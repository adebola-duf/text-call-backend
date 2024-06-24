# run this before running the script on windows

# $env:GOOGLE_APPLICATION_CREDENTIALS='c:/users/bolexyro/downloads/file.json'
# on macos / linux
# export GOOGLE_APPLICATION_CREDENTIALS="/home/user/Downloads/service-account-file.json"

# to read more
# https://firebase.google.com/docs/cloud-messaging/auth-server#linux-or-macos

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import requests
import firebase_admin._messaging_utils
import firebase_admin.messaging
import uvicorn
import firebase_admin
from firebase_admin import credentials, messaging, firestore_async
from pydantic import BaseModel
from datetime import datetime

import os
from dotenv import load_dotenv
load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

cred = credentials.Certificate(os.getenv("JSON_PATH"))
firebase_app = firebase_admin.initialize_app(cred)
db = firestore_async.client()

API_KEY = os.getenv("API_KEY")
SANDBOX_DOMAIN = os.getenv("SANDBOX_DOMAIN")
RECEPIENT_MAIL = os.getenv("RECEPIENT_MAIL")


class CallData(BaseModel):
    caller_phone_number: str
    callee_phone_number: str
    message_json_string: str
    my_message_type: str
    message_id: str


@app.get(path='/')
def index():
    return True


@app.get(path="/call/{call_status}/{caller_phone_number}")
@app.get(path="/call/{call_status}/{caller_phone_number}/{block_message}")
async def handle_call(call_status: str, caller_phone_number: str, block_message: str | None = None):
    data = {'call_status': call_status}
    if call_status == 'blocked' and block_message:
        data = {'call_status': 'blocked', 'block_message': block_message}
    await manager.send_to(caller_phone_number=caller_phone_number, data=data)


@app.post(path='/end-call')
async def end_call(call_data: "CallData"):

    doc_ref = db.collection("users").document(
        call_data.callee_phone_number)
    doc = await doc_ref.get()
    document = doc.to_dict()

    message = messaging.Message(
        android=messaging.AndroidConfig(priority='high'),
        data={
            'purpose': 'end_call',
            'message_id': call_data.message_id,
            'message_json_string': call_data.message_json_string,
            'caller_phone_number': call_data.caller_phone_number,
            'my_message_type': call_data.my_message_type,

        },
        token=document['fcmToken'],
    )
    response = messaging.send(message)
    print('Successfully sent message:', response, flush=True)


@app.get(path='/send-access-request/{requester_phone_number}/{requestee_phone_number}/{message_id}')
async def send_access_request(requester_phone_number: str, requestee_phone_number: str, message_id: str):
    doc_ref = db.collection("users").document(
        requestee_phone_number)
    doc = await doc_ref.get()
    document = doc.to_dict()
    message = messaging.Message(android=messaging.AndroidConfig(priority='high', ttl=60), data={
                                'purpose': 'access_request', 'requester_phone_number': requester_phone_number, 'message_id': message_id},
                                token=document['fcmToken'])
    response = messaging.send(message)
    print('Successfully sent message:', response, flush=True)


@app.get(path='/request_status/{request_status}/{requester_phone_number}/{requestee_phone_number}/{message_id}')
async def handle_request_status(request_status: str, requester_phone_number: str, requestee_phone_number: str, message_id: str):
    doc_ref = db.collection("users").document(
        requester_phone_number)

    doc = await doc_ref.get()
    document = doc.to_dict()

    message = messaging.Message(android=messaging.AndroidConfig(priority='high'),
                                data={'purpose': 'request_status', 'requestee_phone_number': requestee_phone_number,
                                      'message_id': message_id, 'access_request_status': request_status},
                                token=document['fcmToken'],)

    response = messaging.send(message)
    print('Successfully sent message:', response, flush=True)


class ConnectionManager:
    def __init__(self):
        # this dictionary is to store phone number - websocket objects mappings
        self.caller_phone_number_websocket_dict: dict[str, WebSocket] = {}

    async def connect(self, websocket: WebSocket, caller_phone_number: str):
        await websocket.accept()
        self.caller_phone_number_websocket_dict[caller_phone_number] = websocket

    def disconnect(self, websocket: WebSocket):
        phone_number_websocket_connection_to_delete = None
        for phone_number, websocket_connection in self.caller_phone_number_websocket_dict.items():
            if websocket_connection == websocket:
                phone_number_websocket_connection_to_delete = phone_number
        del self.caller_phone_number_websocket_dict[phone_number_websocket_connection_to_delete]

    async def send_to(self, caller_phone_number: str, data: dict):
        if (caller_phone_number in self.caller_phone_number_websocket_dict):
            await self.caller_phone_number_websocket_dict[caller_phone_number].send_json(data)


manager = ConnectionManager()


# return whether we can call or not
def check_last_called_time_for_callee(document: dict) -> bool:
    last_called_time_string = document.get('lastCalledTime')
    if (last_called_time_string == None):
        return True
    last_called_time_datetime: datetime = datetime.strptime(
        last_called_time_string, '%Y-%m-%d %H:%M:%S.%f')
    now = datetime.now()
    time_difference = now - last_called_time_datetime

    if (time_difference.seconds < 20):
        return False

    return True


@app.websocket("/ws/{caller_phone_number}")
async def websocket_endpoint(websocket: WebSocket, caller_phone_number: str):
    await manager.connect(websocket, caller_phone_number)
    try:
        while True:
            data = await websocket.receive_json()
            call_data = CallData.model_validate(data)
            print(call_data, flush=True)

            doc_ref = db.collection("users").document(
                call_data.callee_phone_number)
            doc = await doc_ref.get()

            document = doc.to_dict()
            print(f"Document data: {document}", flush=True)
            # https://firebase.google.com/docs/cloud-messaging/concept-options#data_messages

            if (check_last_called_time_for_callee(document=document)):
                try:
                    message = messaging.Message(
                        android=messaging.AndroidConfig(priority='high'),
                        data={
                            'purpose': 'text_call',
                            'message_id': call_data.message_id,
                            'message_json_string': call_data.message_json_string,
                            'caller_phone_number': call_data.caller_phone_number,
                            'my_message_type': call_data.my_message_type,

                        },
                        token=document['fcmToken'],
                    )

                    # Send a message to the device corresponding to the provided registration token.
                    # Response is a message ID string.
                    response = messaging.send(message)
                    await doc_ref.update(
                        {
                            "lastCalledTime": datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')
                        }
                    )
                    print('Successfully sent message:', response, flush=True)

                except firebase_admin.messaging.UnregisteredError as e:
                    print(f'Firebase Notification Failed. {e}')
                    new_data = {'call_status': 'error'}
                    await manager.send_to(caller_phone_number=caller_phone_number, data=new_data)

            else:
                await manager.send_to(caller_phone_number=caller_phone_number, data={'call_status': 'callee_busy'})

    except WebSocketDisconnect:
        manager.disconnect(websocket)

# this endpoint is just a temporary one until I find out how to hide api keys in flutter.


@app.get(path='/submit-feedback/subject/body')
def send_feedback(subject: str, body: str):

    sender_email = f'sandbox@{SANDBOX_DOMAIN}'
    url = f'https://api.mailgun.net/v3/{SANDBOX_DOMAIN}/messages'

    data = {
        'from': sender_email,
        'to': RECEPIENT_MAIL,
        'subject': subject,
        'text': body
    }

    # Send the POST request
    response = requests.post(
        url,
        auth=('api', API_KEY),
        data=data
    )
    return {"status": response.status_code, "response": response.text}


if __name__ == "__main__":
    uvicorn.run(app=app, host='0.0.0.0')
