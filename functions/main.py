# Welcome to Cloud Functions for Firebase for Python!
# To get started, simply uncomment the below code or create your own.
# Deploy with `firebase deploy`

from firebase_functions import https_fn
from firebase_admin import initialize_app, firestore
from google.cloud.secretmanager import SecretManagerServiceClient
import openai
from typing import Any, Dict, List
import json
from flask import jsonify
from message import Message, Persona
import asyncio

initialize_app()
model = "gpt-3.5-turbo"
magic_word_for_no_reply = "__NO_REPLY__"

cors_headers = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "3600",
}

def get_propmpt_from_firestore(persona: Persona, version: int | None) -> str:
    db = firestore.client()
    try:
        if version is None:
            docs = db.collection(persona.value).order_by("version", direction=firestore.Query.DESCENDING).limit(1).get()
        else:
            query = db.collection(persona.value).where("version", "==", str(version))
            docs = query.get()
    except Exception as e:
        raise Exception(f"Failed to get prompt for {persona.value} with version {version}: {e}")
    if len(docs) == 0:
        raise Exception(f"Failed to get prompt for {persona.value} with version {version}")
    try:
       prompt = docs[0].to_dict()["content"]
    except Exception as e:
        raise Exception(f"Failed to get prompt for {persona.value} with version {version}: {e}")
    if prompt is None:
        raise Exception(f"None prompt detected: Failed to get prompt for {persona.value} with version {version}")

    return prompt

async def ask_openai(prompt: str, messages: List[Message], model: str = "gpt-3.5-turbo") -> Dict[str, Any]:
    try:
        message_dicts = [message.to_openai() for message in messages]
    except Exception as e:
        raise Exception(f"Failed to convert messages to OpenAI format: {e}")

    try:
        valid_message_dicts = [message_dict for message_dict in message_dicts if message_dict is not None]
    except Exception as e:
        raise Exception(f"Failed to filter out invalid messages: {e}")
    try:
        response = await openai.ChatCompletion.acreate(
            model=model,
            temperature=0.5,
            messages=[
                {
                    "role": "system", 
                    "content": prompt,
                },
                *valid_message_dicts,
            ],
        )
    except Exception as e:
        raise Exception(f"Failed to ask OpenAI: {e}")
    return response

async def ask_persona(persona: Persona, messages: List[Message], model: str = "gpt-3.5-turbo") -> Message:
    try:
        prompt = get_propmpt_from_firestore(persona, None)
    except Exception as e:
        print(f"Failed to get prompt for persona {persona.value}: {e}")
        return None
    try:
        response_dict = await ask_openai(prompt, messages, model)
    except Exception as e:
        print(f"Failed to ask persona {persona.value}: {e}")
        return None
    try:
        response_text = parse_openai_response_dict(response_dict)
    except Exception as e:
        print(f"Failed to parse response from persona {persona.value}: {e}")
        return None
    try:
        response = Message(persona, response_text)
    except Exception as e:
        print(f"Failed to create message from response from persona {persona.value}: {e}")
    return response

async def ask_multiple_personas(messages_dict: Dict[Persona, List[Message]], model: str = "gpt-3.5-turbo") -> List[Message]:
    tasks = []
    for persona, messages in messages_dict.items():
        tasks.append(asyncio.create_task(ask_persona(persona, messages, model)))
    responses = await asyncio.gather(*tasks)
    valid_responses = [response for response in responses if response is not None]
    return valid_responses


def parse_openai_response_dict(response: Dict[str, Any]):
    choices = response["choices"]
    choice = choices[0]
    message = choice["message"]
    return message["content"]

@https_fn.on_request()
def lingua_franca_openai_proxy(req: https_fn.Request) -> https_fn.Response:
    # Ignore CORS preflight requests
    if req.method == "OPTIONS":
        return https_fn.Response(
            headers=cors_headers,
            response="OK",
            status=204,
        )
   
    # Parse request JSON
    try:
        req_json = req.get_json()
    except Exception as e:
        return https_fn.Response(
            headers=cors_headers,
            response=f"Failed to parse request JSON: {e}", 
            status=400,
        )
    try:
        messages = req_json["messages"]
    except KeyError as e:
        print(e)
        return https_fn.Response(
            headers=cors_headers,
            response="Failed to get \"messages\" from request JSON: {e}",
            status=400,
        )
    try:
        messages = [Message.from_dict(message) for message in messages]
    except Exception as e:
        return https_fn.Response(
            headers=cors_headers,
            response=f"Failed to parse messages: {e}", 
            status=400,
        )

    
    # Get OpenAI API key from Google Secret Manager
    secret_client = SecretManagerServiceClient()
    try:
        openai.api_key = secret_client.access_secret_version(name="projects/473139429425/secrets/openai-api/versions/latest").payload.data.decode("utf-8").rstrip()
    except Exception as e:
        return https_fn.Response(
            headers=cors_headers,
            response=f"Failed to get OpenAI API key: {e}", 
            status=500,
        )
    
    conversation_messages = [message for message in messages if message.persona in [Persona.user, Persona.chat]]
    num_history_messages = 10
    conversation_messages = conversation_messages[-num_history_messages:] if len(conversation_messages) > num_history_messages else conversation_messages
    current_message = messages[-1:]
    requests_per_persona = {
        Persona.chat: conversation_messages,
        Persona.grammar: current_message,
        Persona.vocab: current_message,
        Persona.politeness: current_message,
        Persona.context: conversation_messages,
    }

    print("persona-messages dump")
    for persona, messages in requests_per_persona.items():
        print(f"persona: {persona.value}")
        for message in messages:
            print(f"message: {message.content}")

    responses_per_persona = asyncio.run(ask_multiple_personas(requests_per_persona))
    valid_responses_per_persona = [r for r in responses_per_persona if magic_word_for_no_reply not in r.content]
    response_dicts_per_persona = [response.to_dict() for response in valid_responses_per_persona]
    response_dict = {"responses": response_dicts_per_persona}
    print("response dict dump: ")
    print(json.dumps(response_dict, indent=2))
    response = jsonify(response_dict)
    response.headers = cors_headers
    return response
