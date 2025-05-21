\
import os
import base64
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from email.mime.text import MIMEText
from dotenv import load_dotenv

load_dotenv()

SCOPES = ['https://www.googleapis.com/auth/gmail.send']

def get_gmail_service():
    creds = None
    # Ensure 'secret' directory exists at the project root or adjust path as needed
    token_path = 'secret/token.json'
    credentials_path = 'secret/credentials.json'

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(credentials_path):
                print(f"[錯誤] '{credentials_path}' 檔案未找到。請從 Google Cloud Console 下載。")
                raise FileNotFoundError(f"'{credentials_path}' not found. Please download it from Google Cloud Console.")
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    service = build('gmail', 'v1', credentials=creds)
    return service

def send_email_notify(subject, body):
    mail_to = os.getenv('MAIL_TO')
    mail_from = os.getenv('MAIL_FROM')

    if not mail_to:
        print('[警告] .env 檔案缺少 MAIL_TO 設定，無法發送通知郵件。')
        return
    try:
        service = get_gmail_service()
        message = MIMEText(body, 'plain', 'utf-8')
        message['to'] = mail_to
        if mail_from:
            message['from'] = mail_from
        message['subject'] = subject
        
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': raw_message}
        
        send_message_response = (service.users().messages().send(userId="me", body=create_message).execute())
        print(f'[通知] 郵件已發送至 {mail_to}, Message Id: {send_message_response["id"]}')
    except FileNotFoundError as fnf_error:
        # Specific handling for missing credentials.json from get_gmail_service
        print(f'[錯誤] 郵件發送前置作業失敗: {fnf_error}')
    except Exception as e:
        print(f'[錯誤] 郵件發送失敗 (Gmail API): {e}')
        if "invalid_grant" in str(e).lower() or "token has been expired or revoked" in str(e).lower():
            print("[提示] Gmail API 憑證可能已失效。請嘗試刪除 'token.json' 檔案後重新執行程式以重新驗證。")
        elif "file not found" in str(e).lower() and "credentials.json" in str(e).lower(): # Should be caught by get_gmail_service
            print("[錯誤] 找不到 'credentials.json' 檔案。請確保該檔案與您的應用程式在同一個目錄下，並且已正確設定。")
            print("       您可以從 Google Cloud Console 下載您的 OAuth 2.0 用戶端憑證。")
