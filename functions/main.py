# Welcome to Cloud Functions for Firebase for Python!
# To get started, simply uncomment the below code or create your own.
# Deploy with `firebase deploy`

from firebase_functions import https_fn
from firebase_admin import initialize_app, get_app, firestore
from google.cloud.secretmanager import SecretManagerServiceClient
import openai
from typing import Any, Dict, List
import json
from flask import jsonify


initialize_app()
model = "gpt-3.5-turbo"

cors_headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "3600",
}

def get_propmpt_from_firestore(prompt_collection: str, version: int | None) -> str:
    db = firestore.client()
    try:
        if version is None:
            docs = db.collection(prompt_collection).order_by("version", direction=firestore.Query.DESCENDING).limit(1).get()
        else:
            query = db.collection(prompt_collection).where("version", "==", str(version))
            docs = query.get()
    except Exception as e:
        raise Exception(f"Failed to get prompt for {prompt_collection} with version {version}: {e}")
    if len(docs) == 0:
        raise Exception(f"Failed to get prompt for {prompt_collection} with version {version}")
    version = docs[0].to_dict()["version"] if version is None else version
    prompt = docs[0].to_dict()["content"]
    print(f"Got prompt for {prompt_collection} with version {version}: {prompt}")
    return prompt

@https_fn.on_request()
def lingua_franca_openai_proxy(req: https_fn.Request) -> https_fn.Response:
    if req.method == "OPTIONS":
        print("Detected CORS preflight request, returning 204...")
        return https_fn.Response(
            headers=cors_headers,
            response="OK",
            status=204,
        )

    secret_client = SecretManagerServiceClient()
    try:
        openai.api_key = secret_client.access_secret_version(name="projects/473139429425/secrets/openai-api/versions/latest").payload.data.decode("utf-8").rstrip()
    except Exception as e:
        return https_fn.Response(
            headers=cors_headers,
            response=f"Failed to get OpenAI API key: {e}", 
            status=500)
    try:
        req_json = req.get_json()
    except Exception as e:
        return https_fn.Response(
            headers=cors_headers,
            response=f"Failed to parse request JSON: {e}", 
            status=400,
        )
    if "messages" not in req_json:
        msg = "Missing \"messages\" field in request JSON"
        print(msg)
        return https_fn.Response(
            headers=cors_headers,
            response=msg, 
            status=400,
        )
    messages = req_json["messages"]
    if "student_language" not in req_json:
        msg = "Missing \"student_language\" field in request JSON"
        print(msg)
        return https_fn.Response(
            headers=cors_headers,
            response=msg, 
            status=400)
    student_language = req_json["student_language"]

    if "last_user_message_id" not in req_json:
        msg = "Missing \"last_user_message_id\" field in request JSON"
        print(msg)
        return https_fn.Response(
            headers=cors_headers,
            response=msg, 
            status=400)
    last_user_message_id = req_json["last_user_message_id"]

    # Message slicing is done by client now.
    previous_messages: List[Dict[str, str]] = messages
    latest_user_message_candidates = [message for message in previous_messages if message["id"] == last_user_message_id]
    if len(latest_user_message_candidates) == 0:
        msg = f"Could not find message with id {last_user_message_id}"
        print(msg)
        return https_fn.Response(
            headers=cors_headers,
            response=msg, 
            status=400)
    latest_user_message = latest_user_message_candidates[0]

    # This loop also removes the "id" field from the `latest_user_message`
    for message in previous_messages:
        del message["id"]

    print("Creating reply response...")
    try:
        reply_system_prompt = get_propmpt_from_firestore("reply-system", None)
    except Exception as e:
        return https_fn.Response(
            headers=cors_headers,
            response=f"Failed to get reply system prompt: {e}", 
            status=500,
        )
    try:
        feedback_system_prompt = get_propmpt_from_firestore("feedback-system", None)
    except Exception as e:
        return https_fn.Response(
            headers=cors_headers,
            response=f"Failed to get feedback system prompt: {e}", 
            status=500,
        )
    
    reply_response = openai.ChatCompletion.create(
        model=model,
        temperature=0.5,
        messages=[
            {
                "role": "system", 
                "content": reply_system_prompt,
            },
            *previous_messages,
        ],
    )
    print("Creating feedback response...")
    feedback_response = openai.ChatCompletion.create(
        model=model,
        temperature=0.5,
        messages=[
            {
                "role": "system", 
                "content": feedback_system_prompt.format(student_language=student_language),
            },
            latest_user_message,
            # *previous_messages,
        ],
    )
    def parse_openai_response_dict(response: Dict[str, Any]):
        print("Tyring to parse response dict...")
        print("Response dict dump: " + json.dumps(response, indent=2))
        if "choices" not in response:
            return None
        choices = response["choices"]
        if len(choices) == 0:
            return None
        choice = choices[0]
        if "message" not in choice:
            return None
        message = choice["message"]
        if "content" not in message:
            return None
        return message["content"]

        
    reply_text = parse_openai_response_dict(reply_response)
    feedback_text = parse_openai_response_dict(feedback_response)

    reply_text = "FAILED TO REPLY" if reply_text is None else reply_text
    feedback_text = "FAILED TO FEEDBACK" if feedback_text is None else feedback_text
    response_dict = {
        "reply": reply_text,
        "feedback": feedback_text,
    }
    print("response dict dump: ")
    print(json.dumps(response_dict, indent=2))
    response = jsonify(response_dict)
    response.headers = cors_headers
    # response.status = 200
    return response
