import uvicorn

if __name__ == "__main__":
    uvicorn.run("docs_chatbot.app:app_factory", factory=True, host="127.0.0.1", port=8000)
