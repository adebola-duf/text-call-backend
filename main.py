# run this before running the script on windows

# $env:GOOGLE_APPLICATION_CREDENTIALS='c:/users/bolexyro/downloads/file.json'
# on macos / linux
# export GOOGLE_APPLICATION_CREDENTIALS="/home/user/Downloads/service-account-file.json"

# to read more
# https://firebase.google.com/docs/cloud-messaging/auth-server#linux-or-macos

from fastapi import FastAPI, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware

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


@app.post(path='/call-user/')
async def call_user(call_data: CallData):
    doc_ref = db.collection("users").document(call_data.callee_phone_number)
    doc = await doc_ref.get()

    if doc.exists:
        document = doc.to_dict()
        print(f"Document data: {document}")
        message = messaging.Message(
            notification=messaging.Notification(title=f'{call_data.caller_phone_number} is calling'),data={'message': call_data.message}, token=document['fcmToken'],)

        # Send a message to the device corresponding to the provided registration token.
        response = messaging.send(message)
        # Response is a message ID string.
        print('Successfully sent message:', response)

        return {'message': 'call sent successfully'}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail='Number doesn\t exist')


if __name__ == "__main__":
    uvicorn.run(app=app, host='0.0.0.0')