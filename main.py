# run this before running the script on windows

# $env:GOOGLE_APPLICATION_CREDENTIALS='c:/users/bolexyro/downloads/file.json'
# on macos / linux
# export GOOGLE_APPLICATION_CREDENTIALS="/home/user/Downloads/service-account-file.json"

# to read more
# https://firebase.google.com/docs/cloud-messaging/auth-server#linux-or-macos

from fastapi import FastAPI, status, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import json
import uvicorn
import firebase_admin
from firebase_admin import credentials, messaging, firestore_async
from pydantic import BaseModel
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


@app.get(path='/')
def index():
    return True


class CallData(BaseModel):
    caller_phone_number: str
    callee_phone_number: str
    message: str
    background_color: dict


@app.get(path="/call/{call_status}/{caller_phone_number}")
async def handle_call(call_status: str,caller_phone_number: str):
    if call_status == 'rejected':
        data = {'message': 'I doth decline the call with utmost regret.', 'call_status': call_status}
    elif call_status == 'accepted':
        data = {'message': 'I hath indeed heeded the beckoning of the telephone.', 'call_status': call_status}

    await manager.send_to(caller_phone_number=caller_phone_number, data=data)


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
        await self.caller_phone_number_websocket_dict[caller_phone_number].send_json(data)


manager = ConnectionManager()

@app.websocket("/ws/{caller_phone_number}")
async def websocket_endpoint(websocket: WebSocket, caller_phone_number: str):
    await manager.connect(websocket, caller_phone_number)
    try:
        while True:
            data = await websocket.receive_json()
            call_data = CallData.model_validate(data)
            print(call_data, flush=True)

            doc_ref = db.collection("users").document(call_data.callee_phone_number)
            doc = await doc_ref.get()
          
            document = doc.to_dict()
            print(f"Document data: {document}", flush=True)
            message = messaging.Message(
                notification=messaging.Notification(title=f'{call_data.caller_phone_number} is calling'),data={'message': call_data.message, 'caller_phone_number': call_data.caller_phone_number, 'background_color': json.dumps(call_data.background_color)}, token=document['fcmToken'],)

            # Send a message to the device corresponding to the provided registration token.
            response = messaging.send(message)
            # Response is a message ID string.
            print('Successfully sent message:', response, flush=True)

    except WebSocketDisconnect:
        manager.disconnect(websocket)

if __name__ == "__main__":
    uvicorn.run(app=app, host='0.0.0.0')
