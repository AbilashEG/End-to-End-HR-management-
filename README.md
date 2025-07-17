# 🚀 End-to-End HR Interview Management System

An AI-powered HR Interview Management System built with **Flask** and integrated with **AWS services** such as Amazon S3, Textract, Bedrock (DeepSeek), DynamoDB, and Cognito. This system allows HR professionals to upload resumes, auto-generate interview questions, track candidates, and update interview outcomes.

✨ Screenshots

<img width="1802" height="979" alt="image" src="https://github.com/user-attachments/assets/c184dc2b-e385-4a06-b4f2-a204f22cfd53" />
<img width="1312" height="759" alt="image" src="https://github.com/user-attachments/assets/2b5549df-8d44-499d-9ea3-59d17b05a4c2" />
<img width="1886" height="962" alt="image" src="https://github.com/user-attachments/assets/4d014e5e-a530-459c-bc18-663d50abe9be" />
<img width="1638" height="969" alt="image" src="https://github.com/user-attachments/assets/0e907dd2-abc4-4b9a-8143-899fa09c6636" />
<img width="1502" height="779" alt="image" src="https://github.com/user-attachments/assets/ab185dec-d1fe-46be-a115-69ab36cafa4f" />







---

## 🏗️ Project Features

- 🔐 **User Authentication** via Amazon Cognito
- 📄 **Resume Upload** with S3 bucket storage
- 📑 **Resume Text Extraction** using Amazon Textract
- 🧠 **Interview Question Generation** using Amazon Bedrock (DeepSeek)
- 🗃️ **Candidate Profile Storage** in DynamoDB
- 📋 **Dashboard View** with status updates, resume preview, and interview logs
- 🎨 **Modern UI** using Bootstrap 5.3 + CSS animations

---

## ⚙️ Tech Stack

| Layer         | Technology             |
|---------------|------------------------|
| Backend       | Python (Flask)         |
| Authentication| AWS Cognito            |
| Storage       | Amazon S3              |
| OCR/Parsing   | Amazon Textract        |
| AI Generator  | Amazon Bedrock (DeepSeek) |
| Database      | Amazon DynamoDB        |
| UI/Frontend   | HTML, CSS, Bootstrap 5.3 |

---

## 🔐 AWS Setup Required

1. **Cognito**: Create User Pool & App Client. Save `COGNITO_CLIENT_ID`, `COGNITO_DOMAIN`.
2. **S3**: Create `smart-hr-resumes` bucket and attach IAM policies to allow uploading/resume reading.
3. **Textract**: Ensure IAM user has `AmazonTextractFullAccess`.
4. **Bedrock**: Use `deepseek.r1-v1:0` with correct `modelId` (not inference profile ID).
5. **DynamoDB**: Create table `SmartHR_Candidates` with `candidate_id` as primary key.

---

## 📁 Project Structure
END-to-END-HR-management/
│
├── templates/
│ ├── login.html
│ ├── dashboard.html
│ └── candidatedetail.html
│
├── static/
│ ├── styles.css
│
├── app.py
├── .env
├── requirements.txt
└── README.md


---

## 🧪 How to Run Locally

```bash
# Clone the repository
git clone https://github.com/your-username/HR-Interview-System.git
cd HR-Interview-System

# Create virtual environment (optional)
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Run the Flask app
python app.py










