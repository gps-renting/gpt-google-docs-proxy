from flask import Flask, request, jsonify
import json
import os
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import requests
import re
import numpy as np
from openai import OpenAI

CACHE_FILE = "embedding_cache.json"

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

def split_by_sections(text):
    sections = []
    matches = list(re.finditer(r'##\s+(.*)', text))
    for i, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        section_text = text[start:end].strip()
        if section_text:
            sections.append({
                "title": title,
                "text": section_text
            })
    return sections
    
def get_embedding(text):
    response = client.embeddings.create(
        input=[text],
        model="text-embedding-3-small"
    )
    return response.data[0].embedding

def cosine_similarity(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f)


def fetch_doc_text(doc_id):
    try:
        credentials_info = json.loads(os.environ['SERVICE_ACCOUNT_JSON'])
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info,
            scopes=["https://www.googleapis.com/auth/documents.readonly"]
        )
        credentials.refresh(Request())

        headers = {
            'Authorization': f'Bearer {credentials.token}'
        }

        url = f'https://docs.googleapis.com/v1/documents/{doc_id}'
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
            raise Exception(f"Failed to fetch doc: {response.text}")

        doc_data = response.json()

        text = ""
        for element in doc_data.get("body", {}).get("content", []):
            paragraph = element.get("paragraph")
            if not paragraph:
                continue
            for el in paragraph.get("elements", []):
                text += el.get("textRun", {}).get("content", "")

        return {
            "title": doc_data.get('title', 'Untitled Document'),
            "text": text.strip()
        }

    except Exception as e:
        raise e


app = Flask(__name__)

@app.route('/get-doc', methods=['GET'])
def get_doc():
    doc_id = request.args.get('docId')
    if not doc_id:
        return jsonify({'error': 'Missing docId'}), 400

    try:
        result = fetch_doc_text(doc_id)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/search-docs', methods=['POST'])
def search_docs():
    data = request.get_json()
    query = data.get("query")
    doc_id = data.get("docId") or os.environ.get("DEFAULT_DOC_ID")

    if not query:
        return jsonify({"error": "Missing query"}), 400
    if not doc_id:
        return jsonify({"error": "Missing docId and no default set"}), 400

    try:
        doc_data = fetch_doc_text(doc_id)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    text = doc_data["text"]
    sections = split_by_sections(text)
    cache = load_cache()
    query_embedding = get_embedding(query)

    for section in sections:
        # Create a unique cache key using title and content hash
        cache_key = section["title"] + "|" + str(hash(section["text"]))

        if cache_key in cache:
            section["embedding"] = cache[cache_key]
        else:
            section["embedding"] = get_embedding(section["text"])
            cache[cache_key] = section["embedding"]

        section["score"] = cosine_similarity(query_embedding, section["embedding"])

    save_cache(cache)

    top_match = max(sections, key=lambda x: x["score"])

    return jsonify({
        "results": [{
            "docTitle": top_match["title"],
            "answer": top_match["text"],
            "link": f"https://docs.google.com/document/d/{doc_id}"
        }]
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

