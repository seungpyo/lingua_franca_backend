# Single Message Format

```json
{
    "persona": "string",
    "content": "string",
}
```
`persona` : One of `user`, `chat`, `grammar`, `vocab`, `politeness`, `context`


`content` : The content of message, written by `persona`


## Examples
```json
{
    "persona": "user",
    "content": "Hello, how are you?"
}
```



# OpenAI Proxy Request 

```json
{
    "messages": [
        {
            "persona": "string",
            "content": "string",
        },
        // some more messages
    ]
}
```
`messages` has a list of messages, each of which is a JSON object with the same format as `Single Message Format`.
The messages MUST be sorted in the order of time, with the oldest message first.

# OpenAI Proxy Response Body

```json
{
    "responses": [
        {
            "persona": "string",
            "content": "string",
        },
        // some more messages
    ]
}
```
`responses` : The list of messages returned by OpenAI API. It is a list of messages, each of which is a JSON object with the same format as `Single Message Format`.
The reponses may include a subset of replies from `chat`, `grammar`, `vocab`, `politeness`, `context` personas. The `chat` persona is always included in the responses, and the other personas are included only when their `content` does not include a magic string `__NO_REPLY__`. The magic string is given by Open AI API and the prompt, so the proxy should not hardcode it.



