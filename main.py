
import os
from time import sleep
from datetime import datetime
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError



def drive_sift(service, page_token=None, items=[]):
    drive_service = service

    while True:
        try:
            # including permissions in the files fields will limit the pageSize to 100.
            # including parents will limit it to 360.
            files = drive_service.files().list(q="'me' in owners", pageSize=1000,
                                               fields="nextPageToken, files(id, name, mimeType, parents, "
                                                                            "webViewLink, owners/emailAddress, "
                                                                            "shared, permissions)",
                                               pageToken=page_token).execute()
            items += files.get('files', [])
            page_token = files.get('nextPageToken', None)

            if page_token is None:
                break

        except HttpError as err:
            print(err)
            if err.resp.status >= 403:
                back_off(drive_sift(drive_service, items, page_token), 1)
        except Exception as err:
            print(err)

    return items


def back_off(function, time):
    print("Error 500 waiting {} seconds and retrying...".format(time))
    sleep(time)

    try:
        return (function)
    except:
        time = time * 5
        return (back_off(function,time))


def build_sheet (service, title):
    range = "A1"
    spreadsheet = {
        'properties': {
            'title': title
        }}

    spreadsheet = service.spreadsheets().create(body=spreadsheet, fields='spreadsheetId').execute()
    sheetId = spreadsheet.get('spreadsheetId')

    headers = {"values": [
    ["Name",
      "ID",
      "Type",
      "Path",
      "Link",
      "Owner",
      "Editors",
      "Readers"
    ]]}

    service.spreadsheets().values().append(spreadsheetId=sheetId,
                                           range=range,
                                           insertDataOption="OVERWRITE",
                                           valueInputOption="RAW",
                                           body=headers).execute()

    return sheetId


def build_path(drive_service, parent_id, all_files,  other_folders=[], path = ""):
    folder_name = ""
    parent_found = False

    try:
        while True:
            parent = None
            parent_found = False
            for i, dic in enumerate(all_files):
                if dic['id'] == parent_id:
                    folder = all_files[i]
                    folder_name = folder.get('name')
                    parent = folder.get('parents')
                    path = ("{}/{}").format(folder_name, path)
                    parent_found = True
                    break

            if parent_found == False and len(other_folders) > 1:
                for n, other_dic in enumerate(other_folders):
                    if other_dic['id'] == parent_id:
                        folder = other_folders[n]
                        folder_name = folder.get('name')
                        parent = folder.get('parents')
                        path = ("{}/{}").format(folder_name, path)
                        parent_found = True
                        break


            if parent_found == False:
                folder = drive_service.files().get(fileId=parent_id, fields='id, name, parents').execute()
                other_folders.append(folder)
                folder_name = folder.get('name')
                if folder_name == 'Costa Concordia2':
                    print(folder)
                    print(parent)
                parent = folder.get('parents')
                path = ("{}/{}").format(folder_name, path)

            if parent is None:
                break
            else:
                parent_id = parent[0]

    except HttpError as err:
        print(err)
        if err.resp.status >= 403:
            back_off(build_path(parent_id,path,), 1)
        if err.resp.status == 400:
            print ("HTTPS 400 error passing NA path")
            return "NA path error"

    return path, other_folders


def populate_sheet(drive_service, items, list=[], my_drive_id = ""):
    other_folders = []
    try:
        for item in items:
            item_readers = ""
            item_writers = ""

            item_id = str(item.get('id'))
            item_name = str(item.get('name'))
            item_type = str(item.get('mimeType'))
            item_link = str(item.get('webViewLink'))

            item_owner = item.get('owners')
            owner = item_owner[0]
            item_owner = str(owner.get('emailAddress'))

            if item_name == 'Root' or item_name == 'My Drive':
                my_drive_id = item_id
                print ("I am root {}".format(item_id))

            # Builds path for file by finding parents
            item_parents = (item.get('parents'))
            if item_parents is None:
                item_path = "None"
            else:
                item_path, other_folders = build_path(drive_service, item_parents[0], items, other_folders)

            if item.get('shared'):
                perms = item.get('permissions')

                for user in perms:
                    if user.get('type') == 'user':
                        if user.get('role') == 'writer':
                            item_writers += "{} \n".format(user.get('emailAddress'))
                        elif user.get('role') == 'reader':
                            item_readers += "{} \n".format(user.get('emailAddress'))


            # append list with new row of file data.
            list.append([item_name, item_id, item_type, item_path, item_link, item_owner, item_writers, item_readers])
    except Exception as err:
        print(err)

    return list

def add_to_sheet(service, id, range, body):
    try:
        service.spreadsheets().values().append(
            spreadsheetId=id,
            range=range,
            body=body,
            valueInputOption="USER_ENTERED"
            ).execute()

    except HttpError as err:
        print(err)
        back_off(add_to_sheet(service, id, range, body), 1)
        if err.resp.status >= 403:
            back_off(add_to_sheet(service, id, range, body), 1)




if __name__ == '__main__':

    SCOPES = ['https://www.googleapis.com/auth/drive']
    timestamp = datetime.now()
    timestamp = timestamp.strftime("%m/%d/%Y %H:%M")

    sheetTitle = "My U-M Google Drive Files {}".format(timestamp)

    creds = None
    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    # build out Google services for each API
    drive_service = build('drive', 'v3', credentials=creds)
    print("Building Drive Service")

    items = drive_sift(drive_service)
    filelist = populate_sheet(drive_service, items)

    sheets_service = build('sheets', 'v4', credentials=creds)
    print("Building Sheets Service")

    drive_service.files.update(fileId='1KVp9V6NOwoAeVKF_YAhLfopy6nMqmghAAsSnP7astj0', removeParents='1atlcekXcGk70vbaHif2nfDr6Fe63hxph')

    #sheetId = build_sheet(sheets_service, sheetTitle)
    #resource = {"majorDimension": "ROWS", "values": filelist}
    #add_to_sheet(sheets_service, sheetId, 'A2', resource)

    # print ("Visit https://docs.google.com/spreadsheets/d/{} to view  files.".format(sheetId))







