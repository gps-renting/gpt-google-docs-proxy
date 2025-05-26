from flask import Flask, request, jsonify
import json
import os
from google.oauth2 import service_account
from google.auth.transport.requests import Request
import requests

app = Flask(__name__)

@app.route('/get-doc', methods=['GET'])
def get_doc():
    doc_id = request.args.get('docId')
    if not doc_id:
        return jsonify({'error': 'Missing docId'}), 400

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
            return jsonify({'error': 'Failed to retrieve document', 'details': response.text}), 500

        doc_data = response.json()

        # Extract text content
        text = ""
        for element in doc_data.get("body", {}).get("content", []):
            paragraph = element.get("paragraph")
            if not paragraph:
                continue
            for el in paragraph.get("elements", []):
                text += el.get("textRun", {}).get("content", "")

        return jsonify({
            'title': doc_data.get('title', 'Untitled Document'),
            'text': text.strip()
        })

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

