# api/index.py
def handler(request):
    try:
        if request["method"] == "GET":
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "text/html"},
                "body": "<h1>✅ 텔레그램 뉴스봇 작동 중입니다</h1>"
            }

        return {
            "statusCode": 405,
            "body": "Method Not Allowed"
        }
    except Exception as e:
        return {
            "statusCode": 500,
            "body": f"Error: {str(e)}"
        }
