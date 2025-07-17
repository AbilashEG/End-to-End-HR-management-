from flask import Flask, redirect, request, session, render_template, flash, url_for, send_file
import os
import requests
from dotenv import load_dotenv
from werkzeug.utils import secure_filename
import boto3
import json
import traceback
from datetime import datetime
import re
import logging
from io import BytesIO

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'supersecretkey')

# Setup basic logging
logging.basicConfig(level=logging.INFO)

# ENV CONFIGS
COGNITO_DOMAIN = os.getenv("COGNITO_DOMAIN")
COGNITO_CLIENT_ID = os.getenv("COGNITO_CLIENT_ID")
COGNITO_CLIENT_SECRET = os.getenv("COGNITO_CLIENT_SECRET")
COGNITO_REDIRECT_URI = os.getenv("COGNITO_REDIRECT_URI")
COGNITO_LOGOUT_URI = os.getenv("COGNITO_LOGOUT_URI")
AWS_REGION = os.getenv("AWS_REGION")
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
S3_BUCKET = os.getenv("S3_BUCKET")
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID")
DYNAMODB_TABLE_NAME = os.getenv("DYNAMODB_TABLE_NAME", "SmartHR_Candidates")
UPLOAD_FOLDER = 'uploads'
AUTHORIZED_USERS = ["abilasheg", "nikhil"]
DEBUG_LOG = os.getenv("DEBUG_LOG", "false").lower() == "true"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# AWS Clients
s3 = boto3.client("s3", region_name=AWS_REGION,
                  aws_access_key_id=AWS_ACCESS_KEY_ID,
                  aws_secret_access_key=AWS_SECRET_ACCESS_KEY)
textract = boto3.client("textract", region_name=AWS_REGION)
bedrock = boto3.client("bedrock-runtime", region_name=AWS_REGION)
dynamodb = boto3.resource("dynamodb", region_name=AWS_REGION)
table = dynamodb.Table(DYNAMODB_TABLE_NAME)

# Utility function to normalize DynamoDB items
def normalize_candidate(candidate):
    norm = {}
    for k, v in candidate.items():
        if isinstance(v, dict) and 'S' in v:
            norm[k] = v['S']
        else:
            norm[k] = v
    return norm

# Utility to split questions into two categories
def robust_split_questions(questions_raw):
    technical, behavioral = [], []
    current_section = None
    for line in questions_raw.split('\n'):
        line = line.strip()
        if not line or line.lower().startswith("<think"):
            continue
        lwr = line.lower()
        if "technical interview question" in lwr:
            current_section = "tech"
            continue
        if "behavioral interview question" in lwr:
            current_section = "behav"
            continue
        # Remove numbering and bullets
        cleaned = re.sub(r'^((\d+[\.\)]\s+)+)', '', line)
        cleaned = re.sub(r'^\*+\s*', '', cleaned).strip()
        if not cleaned or 'interview question' in cleaned.lower():
            continue
        if current_section == "tech":
            technical.append(cleaned)
        elif current_section == "behav":
            behavioral.append(cleaned)
    return technical[:5], behavioral[:5]

@app.route('/')
def index():
    if 'user' in session:
        return redirect('/dashboard')
    return render_template('login.html')

@app.route('/login')
def login():
    login_url = (
        f"https://{COGNITO_DOMAIN}/login"
        f"?response_type=code&client_id={COGNITO_CLIENT_ID}"
        f"&redirect_uri={COGNITO_REDIRECT_URI}"
    )
    return redirect(login_url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        flash("Login failed: No code returned from Cognito.")
        return redirect(url_for('index'))

    token_url = f"https://{COGNITO_DOMAIN}/oauth2/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": COGNITO_CLIENT_ID,
        "client_secret": COGNITO_CLIENT_SECRET,
        "code": code,
        "redirect_uri": COGNITO_REDIRECT_URI
    }
    headers = {"Content-Type": "application/x-www-form-urlencoded"}

    try:
        tokens_resp = requests.post(token_url, data=data, headers=headers)
        tokens_resp.raise_for_status()
        tokens = tokens_resp.json()
    except Exception as e:
        flash(f"Login failed during token request: {str(e)}")
        return redirect(url_for('index'))

    if "access_token" not in tokens:
        flash("Login failed: No access token returned.")
        return redirect(url_for('index'))

    try:
        user_info_resp = requests.get(
            f"https://{COGNITO_DOMAIN}/oauth2/userInfo",
            headers={"Authorization": f"Bearer {tokens['access_token']}"}
        )
        user_info_resp.raise_for_status()
        user_info = user_info_resp.json()
    except Exception as e:
        flash(f"Failed to retrieve user info: {str(e)}")
        return redirect(url_for('index'))

    session['user'] = user_info
    return redirect('/dashboard')

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/')
    username = session['user'].get('username')
    email = session['user'].get('email')

    if username not in AUTHORIZED_USERS:
        return "<h2>Not Authorized</h2>"

    try:
        raw_candidates = table.scan().get('Items', [])
        candidates = [normalize_candidate(c) for c in raw_candidates]
    except Exception as e:
        logging.error(f"DynamoDB scan error: {e}")
        candidates = []

    return render_template("dashboard.html", username=username, email=email, candidates=candidates)

@app.route('/candidate/<email>')
def view_candidate(email):
    if 'user' not in session:
        return redirect('/')
    username = session['user'].get('username')
    if username not in AUTHORIZED_USERS:
        return "Not authorized"

    try:
        response = table.get_item(Key={'email': email})
        candidate = normalize_candidate(response.get('Item', {}))
    except Exception as e:
        flash(f"Error retrieving candidate: {str(e)}")
        return redirect('/dashboard')

    if not candidate:
        return "<h3>Candidate not found.</h3>"

    questions_raw = candidate.get('questions', '')
    last_updated = candidate.get('last_updated', '')
    technical, behavioral = robust_split_questions(questions_raw)
    if len(technical) < 5 or len(behavioral) < 5:
        flash("⚠️ Less than 5 questions found in one or both sections. Review candidate manually.", "warning")

    return render_template(
        "candidate_detail.html",
        candidate=candidate,
        technical=technical,
        behavioral=behavioral,
        last_updated=last_updated
    )

@app.route('/upload', methods=['POST'])
def upload_resume():
    if 'resume' not in request.files:
        flash("❌ No file uploaded.")
        return redirect('/dashboard')

    file = request.files['resume']
    if file.filename == '':
        flash("❌ Empty file.")
        return redirect('/dashboard')

    if not file.filename.lower().endswith(".pdf"):
        flash("❌ Only PDF files are allowed.")
        return redirect('/dashboard')

    filename = secure_filename(file.filename)
    file_path = os.path.join(UPLOAD_FOLDER, filename)

    try:
        # Save locally
        file.save(file_path)

        # Upload to S3
        s3.upload_file(file_path, S3_BUCKET, filename)

        flash("✅ Resume uploaded. Processing...")

        # Use Textract to extract text
        textract_response = textract.detect_document_text(
            Document={'S3Object': {'Bucket': S3_BUCKET, 'Name': filename}}
        )

        extracted_text = "\n".join(
            block["Text"] for block in textract_response.get("Blocks", [])
            if block["BlockType"] == "LINE"
        ).strip()

        # Extract email from resume
        email_match = re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z]+", extracted_text)
        extracted_email = email_match.group(0) if email_match else None
        if not extracted_email:
            flash("❌ Email not detected in resume.")
            return redirect('/dashboard')

        # Extract candidate name (line before email)
        lines = extracted_text.splitlines()
        extracted_name = "Unknown"
        for i, line in enumerate(lines[:10]):
            if email_match and email_match.group(0) in line and i > 0:
                extracted_name = lines[i-1].strip()
                break

        # Extract phone or default placeholder
        phone_match = re.search(r"\+?\d[\d\s\-]{9,14}", extracted_text)
        extracted_phone = phone_match.group(0) if phone_match else "+91XXXXXXXXXX"

        # Check if candidate exists and if questions are already generated
        existing = table.get_item(Key={"email": extracted_email}).get('Item')
        if existing and existing.get("questions"):
            flash("⚠️ Candidate already exists with questions. Skipping AI question generation.")
            return redirect('/dashboard')

        prompt = f"""
You are an intelligent HR assistant. Based on the resume below, do the following:
### Technical Interview Questions
- Generate exactly 5 Technical questions.
- Number them from 1 to 5.
- Do not include Behavioral style or personal questions.
### Behavioral Interview Questions
- Generate exactly 5 Behavioral questions.
- Number them from 1 to 5.
- Focus on experiences, leadership, team skills, adaptability.
✨ FORMAT:
Return only the 10 numbered questions in their respective sections.
NO extra explanations or comments.
Resume Text:
\"\"\"
{extracted_text[:1500]}
\"\"\"
"""

        payload = {"prompt": prompt, "temperature": 0.7, "top_p": 0.9, "max_tokens": 800}
        bedrock_response = bedrock.invoke_model(
            modelId=BEDROCK_MODEL_ID,
            body=json.dumps(payload),
            contentType="application/json",
            accept="application/json"
        )

        body_stream = bedrock_response.get("body")
        response_body = json.loads(body_stream.read()) if body_stream else {}
        output = (
            response_body.get("output")
            or response_body.get("completion")
            or (response_body.get("choices", [{}])[0].get("text"))
            or (response_body.get("results", [{}])[0].get("outputText"))
            or "⚠️ No output returned."
        ).strip()

        # Save candidate info to DynamoDB
        table.put_item(Item={
            "email": extracted_email,
            "name": extracted_name,
            "phone": extracted_phone,
            "resume_key": filename,
            "skills": ["Python", "AWS", "Communication"],
            "questions": output,
            "interview_status": "Applied",
            "interview_datetime": "To be scheduled",
            "attendance": "Pending",
            "feedback": "",
            "rating": "",
            "last_updated": datetime.now().isoformat()
        })

        flash("✅ AI-generated questions saved.")

    except Exception as e:
        traceback.print_exc()
        flash(f"❌ Error generating questions or processing resume: {str(e)}")

    return redirect('/dashboard')

@app.route('/candidates')
def view_candidates():
    if 'user' not in session:
        return redirect('/')
    if session['user'].get('username') not in AUTHORIZED_USERS:
        return "<h2>Access Denied</h2>"

    try:
        raw_candidates = table.scan().get("Items", [])
    except Exception as e:
        logging.error(f"Error scanning candidates: {e}")
        raw_candidates = []

    candidates = [normalize_candidate(c) for c in raw_candidates]

    return render_template("candidates.html", candidates=candidates)

@app.route('/candidate/update/<email>', methods=['GET', 'POST'])
def update_candidate(email):
    if 'user' not in session:
        return redirect('/')

    if request.method == 'POST':
        try:
            table.update_item(
                Key={"email": email},
                UpdateExpression="""
                    set interview_datetime = :d, interview_status = :s,
                        attendance = :a, feedback = :f, rating = :r
                """,
                ExpressionAttributeValues={
                    ":d": request.form.get('interview_datetime', 'To be scheduled'),
                    ":s": request.form.get('interview_status', 'Applied'),
                    ":a": request.form.get('attendance', 'Pending'),
                    ":f": request.form.get('feedback', ''),
                    ":r": request.form.get('rating', '')
                }
            )
            flash("✅ Candidate updated.")
            return redirect('/candidates')
        except Exception as e:
            flash(f"❌ Update error: {str(e)}")

    try:
        candidate_raw = table.get_item(Key={"email": email}).get("Item", {})
        candidate = normalize_candidate(candidate_raw)
    except Exception as e:
        flash(f"Failed to load candidate: {str(e)}")
        candidate = {}

    return render_template("candidate_update.html", candidate=candidate)

@app.route('/logout')
def logout():
    session.clear()
    logout_url = (
        f"https://{COGNITO_DOMAIN}/logout"
        f"?client_id={COGNITO_CLIENT_ID}"
        f"&logout_uri={COGNITO_LOGOUT_URI}"
    )
    return redirect(logout_url)

@app.route('/goodbye')
def goodbye():
    return render_template('goodbye.html')

# === Secure Resume Download Route ===
@app.route('/resume/download/<filename>')
def download_resume(filename):
    if 'user' not in session or session['user'].get('username') not in AUTHORIZED_USERS:
        flash("Not authorized.")
        return redirect('/dashboard')
    try:
        file_obj = BytesIO()
        s3.download_fileobj(S3_BUCKET, filename, file_obj)
        file_obj.seek(0)
        return send_file(
            file_obj,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename
        )
    except Exception as e:
        logging.error(f"Error downloading file {filename}: {e}")
        flash(f'Failed to download resume: {str(e)}')
        return redirect('/dashboard')

if __name__ == "__main__":
    app.run(debug=True)
