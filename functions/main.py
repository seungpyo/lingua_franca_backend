# Welcome to Cloud Functions for Firebase for Python!
# To get started, simply uncomment the below code or create your own.
# Deploy with `firebase deploy`

from firebase_functions import https_fn
from firebase_admin import initialize_app, get_app
from google.cloud.secretmanager import SecretManagerServiceClient
import openai
from typing import Any, Dict, List
import json
from flask import jsonify


initialize_app()
model = "gpt-3.5-turbo"
reply_system_prompt = f"""
You are an English speaking tutor who is replying to a student's messages on random topics.
Try to reply to the student's messages so that student can learn various English expressions.
Since you are an educator, please use polite and appropriate language.
Your main goal is keep the conversation going, and have student be more engaged in the conversation.
"""
feedback_system_prompt = """
You are an English tutor who gives feedback to a student's messages on random topics.
Try to find out awkward statements, grammar mistakes, or spelling mistakes in the student's messages.
DO NOT say things other than linguistic feedback. If there is no linguistic feedback, just say things like "Good job!".
Since you are an educator, please use polite and appropriate language.
Also, try not to hurt the student's feelings. You may use emojis to soften your feedback.
Since the student is native {student_language} speaker, you MUST reply in {student_language}.
DO NOT just translate student's answer; give some educational feedback so that student can learn English.
"""

@https_fn.on_request()
def lingua_franca_openai_proxy(req: https_fn.Request) -> https_fn.Response:
    secret_client = SecretManagerServiceClient()
    try:
        openai.api_key = secret_client.access_secret_version(name="projects/473139429425/secrets/openai-api/versions/latest").payload.data.decode("utf-8").rstrip()
    except Exception as e:
        return https_fn.Response(response=f"Failed to get OpenAI API key: {e}", status=500)
    try:
        req_json = req.get_json()
    except Exception as e:
        return https_fn.Response(response=f"Failed to parse request JSON: {e}", status=400)
    if "messages" not in req_json:
        msg = "Missing \"messages\" field in request JSON"
        print(msg)
        return https_fn.Response(response=msg, status=400)
    messages = req_json["messages"]
    if "student_language" not in req_json:
        msg = "Missing \"student_language\" field in request JSON"
        print(msg)
        return https_fn.Response(response=msg, status=400)
    student_language = req_json["student_language"]
    # Message slicing is done by client now.
    previous_messages: List[Dict[str, str]] = messages

    print("Creating reply response...")
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
            *previous_messages,
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
    return jsonify(response_dict)
