# api/index.py

def handler(request):
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "text/plain"},
        "body": "Hello from Vercel Python Serverless!"
    }
