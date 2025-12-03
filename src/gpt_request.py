import openai
import time
import random
import os
import base64
from openai import OpenAI
from anthropic import AnthropicFoundry
from google import genai
from google.genai import types
import time
import json
import pathlib


# Read and cache once
_CFG_PATH = pathlib.Path(__file__).with_name("api_config.json")
with _CFG_PATH.open("r", encoding="utf-8") as _f:
    _CFG = json.load(_f)


def cfg(svc: str, key: str, default=None):
    return os.getenv(f"{svc}_{key}".upper(), _CFG.get(svc, {}).get(key, default))


def generate_log_id():
    """Generate a log ID with 'tkb' prefix and current timestamp."""
    return f"tkb{int(time.time() * 1000)}"


def request_claude(prompt, log_id=None, max_tokens=16384, max_retries=3):
    base_url = cfg("claude", "base_url")
    api_key = cfg("claude", "api_key")
    model_name = cfg("claude", "model")

    client = AnthropicFoundry(
        api_key=api_key,
        base_url=base_url
    )

    if log_id is None:
        log_id = generate_log_id()

    retry_count = 0
    while retry_count < max_retries:
        try:
            message = client.messages.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                max_tokens=max_tokens,
            )

            return message.content[0].text.strip()

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)


def request_claude_token(prompt, log_id=None, max_tokens=10000, max_retries=3):
    base_url = cfg("claude", "base_url")
    api_key = cfg("claude", "api_key")
    model_name = cfg("claude", "model")

    client = AnthropicFoundry(
        api_key=api_key,
        base_url=base_url
    )

    if log_id is None:
        log_id = generate_log_id()

    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    retry_count = 0
    while retry_count < max_retries:
        try:
            message = client.messages.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": prompt,
                    }
                ],
                max_tokens=max_tokens,
            )
            # Extract token usage from Anthropic response
            if message.usage:
                usage_info["prompt_tokens"] = message.usage.input_tokens
                usage_info["completion_tokens"] = message.usage.output_tokens
                usage_info["total_tokens"] = message.usage.input_tokens + message.usage.output_tokens
            return message, usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)

    return None, usage_info


def request_gemini_with_video(prompt: str, video_path: str, log_id=None, max_tokens: int = 10000, max_retries: int = 3):
    """
    Makes a multimodal request to the Gemini-2.5 model using video + text.

    Args:
        prompt (str): The user instruction, e.g., "Please evaluate and suggest improvements for this educational animation."
        video_path (str): Local path to the video file (MP4 preferred, <20MB recommended).
        log_id (str, optional): Tracking ID
        max_tokens (int): Max response token length
        max_retries (int): Max retry attempts

    Returns:
        dict: The Gemini model response
    """
    base_url = cfg("gemini", "base_url")
    api_version = cfg("gemini", "api_version")
    api_key = cfg("gemini", "api_key")
    model_name = cfg("gemini", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=api_key,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    # Load and base64-encode video
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    with open(video_path, "rb") as f:
        video_bytes = f.read()

    video_base64 = base64.b64encode(video_bytes).decode("utf-8")
    data_url = f"data:video/mp4;base64,{video_base64}"

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}, "media_type": "video/mp4"},
                        ],
                    }
                ],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )
            return completion

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")
            delay = (2**retry_count) * 0.2 + random.random() * 0.2
            print(f"Retry {retry_count}/{max_retries} after error: {e}, waiting {delay:.2f}s...")
            time.sleep(delay)


def request_gemini_video_img(
    prompt: str, video_path: str, image_path: str, log_id=None, max_tokens: int = 10000, max_retries: int = 3
):
    """
    Makes a multimodal request to the Gemini model using video & ref img + text.
    Uses Google official genai SDK.

    Args:
        prompt (str): The user instruction
        video_path (str): Local path to the video file (MP4 preferred)
        image_path (str): Local path to the reference image
        log_id (str, optional): Tracking ID (unused with Google SDK)
        max_tokens (int): Max response token length
        max_retries (int): Max retry attempts

    Returns:
        response: The Gemini model response
    """
    api_key = cfg("gemini", "api_key")
    model_name = cfg("gemini", "model")

    # Initialize Google genai client
    client = genai.Client(api_key=api_key)

    # Check files exist
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")

    # Upload video file to Gemini
    video_file = client.files.upload(file=video_path)
    
    # Read image as bytes
    with open(image_path, "rb") as f:
        image_bytes = f.read()

    retry_count = 0
    while retry_count < max_retries:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=[
                    prompt,
                    video_file,
                    types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                ],
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                ),
            )
            return response

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")
            delay = (2**retry_count) * 0.2 + random.random() * 0.2
            print(f"Retry {retry_count}/{max_retries} after error: {e}, waiting {delay:.2f}s...")
            time.sleep(delay)
    return None


def request_gemini_video_img_token(
    prompt: str, video_path: str, image_path: str, log_id=None, max_tokens: int = 10000, max_retries: int = 3
):
    """
    Makes a multimodal request to the Gemini-2.5 model using video & ref img + text.

    Args:
        prompt (str): The user instruction, e.g., "Please evaluate and suggest improvements for this educational animation."
        video_path (str): Local path to the video file (MP4 preferred, <20MB recommended).
        log_id (str, optional): Tracking ID
        max_tokens (int): Max response token length
        max_retries (int): Max retry attempts

    Returns:
        dict: The Gemini model response
    """
    base_url = cfg("gemini", "base_url")
    api_version = cfg("gemini", "api_version")
    api_key = cfg("gemini", "api_key")
    model_name = cfg("gemini", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=api_key,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # Load and base64-encode video
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    with open(video_path, "rb") as f:
        video_bytes = f.read()
    video_base64 = base64.b64encode(video_bytes).decode("utf-8")
    video_data_url = f"data:video/mp4;base64,{video_base64}"

    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode("utf-8")
    image_data_url = f"data:image/png;base64,{base64_image}"

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": video_data_url, "detail": "high"},
                                "media_type": "video/mp4",
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": image_data_url, "detail": "high"},
                                "media_type": "image/png",
                            },
                        ],
                    }
                ],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )
            # return completion

            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")
            delay = (2**retry_count) * 0.2 + random.random() * 0.2
            print(f"Retry {retry_count}/{max_retries} after error: {e}, waiting {delay:.2f}s...")
            time.sleep(delay)
    return None, usage_info


def request_gemini(prompt, log_id=None, max_tokens=8000, max_retries=3):
    """
    Makes a request to the gemini-2.5-pro-preview-03-25 model with retry functionality.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 8000
        max_retries (int, optional): Maximum number of retry attempts, default 3

    Returns:
        dict: The model's response
    """
    base_url = cfg("gemini", "base_url")
    api_version = cfg("gemini", "api_version")
    api_key = cfg("gemini", "api_key")
    model_name = cfg("gemini", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=api_key,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )
            return completion
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)


def request_gemini_token(prompt, log_id=None, max_tokens=8000, max_retries=3):
    """
    Makes a request to the gemini-2.5-pro-preview-03-25 model with retry functionality.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 8000
        max_retries (int, optional): Maximum number of retry attempts, default 3

    Returns:
        dict: The model's response
    """

    base_url = cfg("gemini", "base_url")
    api_version = cfg("gemini", "api_version")
    api_key = cfg("gemini", "api_key")
    model_name = cfg("gemini", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=api_key,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )

            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)
    return None, usage_info


def request_gpt4o(prompt, log_id=None, max_tokens=8000, max_retries=3):
    """
    Makes a request to the gpt-4o-2024-11-20 model with retry functionality.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 8000
        max_retries (int, optional): Maximum number of retry attempts, default 3

    Returns:
        dict: The model's response
    """

    base_url = cfg("gpt4o", "base_url")
    api_version = cfg("gpt4o", "api_version")
    ak = cfg("gpt4o", "api_key")
    model_name = cfg("gpt4o", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=ak,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )
            return completion.choices[0].message.content
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)


def request_gpt4o_token(prompt, log_id=None, max_tokens=8000, max_retries=3):
    """
    Makes a request to the gpt-4o-2024-11-20 model with retry functionality.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 8000
        max_retries (int, optional): Maximum number of retry attempts, default 3

    Returns:
        dict: The model's response
    """
    base_url = cfg("gpt4o", "base_url")
    api_version = cfg("gpt4o", "api_version")
    ak = cfg("gpt4o", "api_key")
    model_name = cfg("gpt4o", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=ak,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )

            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)
    return None, usage_info


def request_o4mini(prompt, log_id=None, max_tokens=8000, max_retries=3, thinking=False):
    """
    Makes a request to the o4-mini-2025-04-16 model with retry functionality.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 8000
        max_retries (int, optional): Maximum number of retry attempts, default 3
        thinking (bool, optional): Whether to enable thinking mode, default False

    Returns:
        dict: The model's response
    """
    base_url = cfg("gpt4omini", "base_url")
    api_version = cfg("gpt4omini", "api_version")
    ak = cfg("gpt4omini", "api_key")
    model_name = cfg("gpt4omini", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=ak,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    # Configure extra_body for thinking if enabled
    extra_body = None
    if thinking:
        extra_body = {"thinking": {"type": "enabled", "budget_tokens": 2000}}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
                extra_body=extra_body,
            )
            return completion
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)


def request_o4mini_token(prompt, log_id=None, max_tokens=8000, max_retries=3, thinking=False):
    """
    Makes a request to the o4-mini-2025-04-16 model with retry functionality.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 8000
        max_retries (int, optional): Maximum number of retry attempts, default 3
        thinking (bool, optional): Whether to enable thinking mode, default False

    Returns:
        dict: The model's response
    """
    base_url = cfg("gpt4omini", "base_url")
    api_version = cfg("gpt4omini", "api_version")
    ak = cfg("gpt4omini", "api_key")
    model_name = cfg("gpt4omini", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=ak,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    # Configure extra_body for thinking if enabled
    extra_body = None
    if thinking:
        extra_body = {"thinking": {"type": "enabled", "budget_tokens": 2000}}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
                extra_body=extra_body,
            )

            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)
    return None, usage_info


def request_gpt5(prompt, log_id=None, max_tokens=1000, max_retries=3):
    """
    Makes a request to the gpt-5-chat-2025-08-07 model with retry functionality.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 1000
        max_retries (int, optional): Maximum number of retry attempts, default 3

    Returns:
        dict: The model's response
    """

    base_url = cfg("gpt5", "base_url")
    api_version = cfg("gpt5", "api_version")
    ak = cfg("gpt5", "api_key")
    model_name = cfg("gpt5", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=ak,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )
            return completion
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)


def request_gpt5_token(prompt, log_id=None, max_tokens=1000, max_retries=3):
    """
    Makes a request to the gpt-5-chat-2025-08-07 model with retry functionality.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 1000
        max_retries (int, optional): Maximum number of retry attempts, default 3

    Returns:
        dict: The model's response
    """
    base_url = cfg("gpt5", "base_url")
    api_version = cfg("gpt5", "api_version")
    ak = cfg("gpt5", "api_key")
    model_name = cfg("gpt5", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=ak,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )

            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)
    return None, usage_info


def request_gpt41(prompt, log_id=None, max_tokens=1000, max_retries=3):
    """
    Makes a request to the gpt-4.1-2025-04-14 model with retry functionality.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 1000
        max_retries (int, optional): Maximum number of retry attempts, default 3

    Returns:
        dict: The model's response
    """
    base_url = cfg("gpt41", "base_url")
    api_version = cfg("gpt41", "api_version")
    api_key = cfg("gpt41", "api_key")
    model_name = cfg("gpt41", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=api_key,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )
            return completion
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)


def request_gpt41_token(prompt, log_id=None, max_tokens=1000, max_retries=3):
    """
    Makes a request to the gpt-4.1-2025-04-14 model with retry functionality.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 1000
        max_retries (int, optional): Maximum number of retry attempts, default 3

    Returns:
        dict: The model's response
    """
    base_url = cfg("gpt41", "base_url")
    api_version = cfg("gpt41", "api_version")
    ak = cfg("gpt41", "api_key")
    model_name = cfg("gpt41", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=ak,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}
    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )

            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                # 即使失败也返回，以便主程序可以继续
                print(f"Failed after {max_retries} attempts. Last error: {str(e)}")
                return None, usage_info

            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)

    return None, usage_info


def request_gpt41_img(prompt, image_path=None, log_id=None, max_tokens=1000, max_retries=3):
    """
    Makes a request to the gpt-4.1-2025-04-14 model with optional image input and retry functionality.
    Args:
        prompt (str): The text prompt to send to the model
        image_path (str, optional): Absolute path to an image file to include
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_tokens (int, optional): Maximum tokens for response, default 1000
        max_retries (int, optional): Maximum number of retry attempts, default 3
    Returns:
        dict: The model's response
    """
    base_url = cfg("gpt41", "base_url")
    api_version = cfg("gpt41", "api_version")
    ak = cfg("gpt41", "api_key")
    model_name = cfg("gpt41", "model")

    client = openai.AzureOpenAI(
        azure_endpoint=base_url,
        api_version=api_version,
        api_key=ak,
    )
    if log_id is None:
        log_id = generate_log_id()
    extra_headers = {"X-TT-LOGID": log_id}

    if image_path:
        # 检查图片路径是否存在
        if not os.path.isfile(image_path):
            raise FileNotFoundError(f"Image file not found: {image_path}")

        with open(image_path, "rb") as image_file:
            base64_image = base64.b64encode(image_file.read()).decode("utf-8")

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{base64_image}"}},
                ],
            }
        ]

    else:
        messages = [{"role": "user", "content": prompt}]
    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=max_tokens,
                extra_headers=extra_headers,
            )
            return completion
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)


def request_gpt51(prompt, log_id=None, max_completion_tokens=8000, max_retries=3, max_tokens=None):
    """
    Makes a request to the gpt-5.1 model via Azure OpenAI (OpenAI SDK compatible) with retry functionality.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_completion_tokens (int, optional): Maximum tokens for response, default 8000
        max_retries (int, optional): Maximum number of retry attempts, default 3
        max_tokens (int, optional): Alias for max_completion_tokens (for compatibility)

    Returns:
        dict: The model's response
    """
    # Support max_tokens as alias for compatibility with other models
    if max_tokens is not None:
        max_completion_tokens = max_tokens

    base_url = cfg("gpt51", "base_url")
    api_key = cfg("gpt51", "api_key")
    model_name = cfg("gpt51", "model")

    # Use OpenAI client with Azure OpenAI compatible endpoint
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=max_completion_tokens,
                extra_headers=extra_headers,
            )
            return completion
        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)


def request_gpt51_token(prompt, log_id=None, max_completion_tokens=8000, max_retries=3, max_tokens=None):
    """
    Makes a request to the gpt-5.1 model via Azure OpenAI (OpenAI SDK compatible) with retry functionality.
    Returns both the completion and token usage info.

    Args:
        prompt (str): The text prompt to send to the model
        log_id (str, optional): The log ID for tracking requests, defaults to tkb+timestamp
        max_completion_tokens (int, optional): Maximum tokens for response, default 8000
        max_retries (int, optional): Maximum number of retry attempts, default 3
        max_tokens (int, optional): Alias for max_completion_tokens (for compatibility)

    Returns:
        tuple: (completion, usage_info) - The model's response and token usage statistics
    """
    # Support max_tokens as alias for compatibility with other models
    if max_tokens is not None:
        max_completion_tokens = max_tokens

    base_url = cfg("gpt51", "base_url")
    api_key = cfg("gpt51", "api_key")
    model_name = cfg("gpt51", "model")

    # Use OpenAI client with Azure OpenAI compatible endpoint
    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}
    usage_info = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                max_completion_tokens=max_completion_tokens,
                extra_headers=extra_headers,
            )

            if completion.usage:
                usage_info["prompt_tokens"] = completion.usage.prompt_tokens
                usage_info["completion_tokens"] = completion.usage.completion_tokens
                usage_info["total_tokens"] = completion.usage.total_tokens
            return completion, usage_info

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                print(f"Failed after {max_retries} attempts. Last error: {str(e)}")
                return None, usage_info

            # Exponential backoff with jitter
            delay = (2**retry_count) * 0.1 + (random.random() * 0.1)
            print(
                f"Request failed with error: {str(e)}. Retrying in {delay:.2f} seconds... (Attempt {retry_count}/{max_retries})"
            )
            time.sleep(delay)

    return None, usage_info


def request_gpt51_video_img(
    prompt: str, video_path: str, image_path: str, log_id=None, max_completion_tokens: int = 10000, max_retries: int = 3
):
    """
    Makes a multimodal request to the gpt-5.1 model using video & ref img + text.

    Args:
        prompt (str): The user instruction
        video_path (str): Local path to the video file (MP4 preferred)
        image_path (str): Local path to the reference image file
        log_id (str, optional): Tracking ID
        max_completion_tokens (int): Max response token length
        max_retries (int): Max retry attempts

    Returns:
        dict: The model response
    """
    base_url = cfg("gpt51", "base_url")
    api_key = cfg("gpt51", "api_key")
    model_name = cfg("gpt51", "model")

    client = OpenAI(
        base_url=base_url,
        api_key=api_key,
    )

    if log_id is None:
        log_id = generate_log_id()

    extra_headers = {"X-TT-LOGID": log_id}

    # Load and base64-encode video
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")
    with open(video_path, "rb") as f:
        video_bytes = f.read()
    video_base64 = base64.b64encode(video_bytes).decode("utf-8")
    video_data_url = f"data:video/mp4;base64,{video_base64}"

    # Load and base64-encode image
    if not os.path.isfile(image_path):
        raise FileNotFoundError(f"Image file not found: {image_path}")
    with open(image_path, "rb") as image_file:
        base64_image = base64.b64encode(image_file.read()).decode("utf-8")
    image_data_url = f"data:image/png;base64,{base64_image}"

    retry_count = 0
    while retry_count < max_retries:
        try:
            completion = client.chat.completions.create(
                model=model_name,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": video_data_url, "detail": "high"},
                            },
                            {
                                "type": "image_url",
                                "image_url": {"url": image_data_url, "detail": "high"},
                            },
                        ],
                    }
                ],
                max_completion_tokens=max_completion_tokens,
                extra_headers=extra_headers,
            )
            return completion

        except Exception as e:
            retry_count += 1
            if retry_count >= max_retries:
                raise Exception(f"Failed after {max_retries} attempts. Last error: {str(e)}")
            delay = (2**retry_count) * 0.2 + random.random() * 0.2
            print(f"Retry {retry_count}/{max_retries} after error: {e}, waiting {delay:.2f}s...")
            time.sleep(delay)
    return None


if __name__ == "__main__":

    # Gemini
    # response_gemini = request_gemini("上海天气怎么样？")
    # print(response_gemini.model_dump_json())

    # # GPT-4o
    # response_gpt4o = request_gpt4o("上海天气怎么样？")
    # print(response_gpt4o)

    # # o4-mini
    # response_o4mini = request_o4mini("上海天气怎么样？")
    # print(response_o4mini.model_dump_json())

    # # GPT-4.1
    response_gpt41 = request_gpt41("上海天气怎么样？")
    print(response_gpt41.model_dump_json())

    # GPT-5
    # response_gpt5 = request_gpt5("新加坡天气怎么样？")
    # print(response_gpt5.model_dump_json())

    # # Claude
    # response_claude = request_claude_token("新加坡天气怎么样？")
    # print(response_claude)
