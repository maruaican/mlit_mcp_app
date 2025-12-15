import os
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv
import google.generativeai as genai
import logging
import asyncio

# ロギングの設定
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# .envファイルから環境変数を読み込む
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

# FastAPIアプリケーションのインスタンスを作成
app = FastAPI()

# --- グローバル変数 ---
available_gemini_model = None

@app.on_event("startup")
async def startup_event():
    """
    アプリケーション起動時に、利用可能なGeminiモデルを取得する
    """
    global available_gemini_model
    try:
        logger.info("Fetching available Gemini models...")
        models = [m for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        if not models:
            raise RuntimeError("No models found that support 'generateContent'.")
        
        # モデル名でソートし、最新のモデルを取得
        latest_models = sorted(models, key=lambda m: m.name, reverse=True)
        available_gemini_model = latest_models[0].name
        logger.info(f"Successfully found a suitable Gemini model: {available_gemini_model}")

    except Exception as e:
        logger.error(f"Failed to fetch available Gemini models: {e}", exc_info=True)
        available_gemini_model = "gemini-1.0-pro"
        logger.warning(f"Using fallback Gemini model: {available_gemini_model}")

# 静的ファイル（HTML, CSS, JS）を配信するための設定
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Gemini APIキーを設定
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEYが見つかりません。")
genai.configure(api_key=GEMINI_API_KEY)

# 国土交通省APIのエンドポイントとキーを設定
MLIT_API_ENDPOINT = "https://www.mlit-data.jp/api/v1/graphql"
MLIT_API_KEY = os.getenv("MLIT_API_KEY")
if not MLIT_API_KEY:
    raise ValueError("MLIT_API_KEYが見つかりません。")

# プロキシ設定を環境変数から読み込む
HTTP_PROXY = os.getenv("HTTP_PROXY")
HTTPS_PROXY = os.getenv("HTTPS_PROXY")
proxies = {"http://": HTTP_PROXY, "https://": HTTPS_PROXY} if HTTP_PROXY and HTTPS_PROXY else None

# リクエストのモデルを定義
class QueryRequest(BaseModel):
    question: str

# プロンプトのテンプレート
PROMPT_TEMPLATE = """
以下の自然言語の質問を、国土交通省のGraphQL APIクエリに変換してください、
ユーザーの質問: {question}
---
生成されるクエリは、dataCatalog APIを呼び出す形式にしてください、
"""

@app.post("/api/query")
async def query_data(request: QueryRequest):
    logger.info("API endpoint /api/query called!")
    if not available_gemini_model:
        raise HTTPException(status_code=503, detail="Geminiモデルが利用できません。サーバーログを確認してください。")
        
    try:
        model = genai.GenerativeModel(available_gemini_model)
        
        prompt = PROMPT_TEMPLATE.format(question=request.question)
        
        logger.info(f"Generating GraphQL query with Gemini model: {available_gemini_model}...")
        try:
            response = await asyncio.wait_for(
                model.generate_content_async(prompt), 
                timeout=15.0
            )
            logger.info("Successfully generated content from Gemini.")
        except asyncio.TimeoutError:
            logger.error("Gemini API call timed out.")
            raise HTTPException(status_code=504, detail="Gateway Timeout: The Gemini API did not respond in time. This might be due to a firewall blocking the connection.")

        graphql_query = response.text.strip()
        logger.info(f"Generated GraphQL query: {graphql_query}")

        headers = {
            "Authorization": f"Bearer {MLIT_API_KEY}",
            "Content-Type": "application/json"
        }
        
        logger.info(f"Sending request to MLIT API: {MLIT_API_ENDPOINT}")
        async with httpx.AsyncClient(proxies=proxies) as client:
            mlit_response = await client.post(
                MLIT_API_ENDPOINT, 
                json={"query": graphql_query},
                headers=headers,
                timeout=15.0
            )
            mlit_response.raise_for_status()
        
        logger.info("Successfully received response from MLIT API.")
        return mlit_response.json()

    except httpx.TimeoutException as e:
        logger.error(f"MLIT APIへのリクエストがタイムアウトしました: {e}")
        raise HTTPException(status_code=504, detail="Gateway Timeout: The MLIT API did not respond in time.")
    except httpx.RequestError as e:
        logger.error(f"MLIT APIへのリクエストでエラーが発生しました: {e}")
        raise HTTPException(status_code=502, detail=f"Bad Gateway: An error occurred while communicating with the MLIT API. Details: {e}")
    except Exception as e:
        logger.error(f"予期せぬエラーが発生しました: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"An unexpected error occurred. Details: {str(e)}")

@app.get("/")
async def read_root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/static/index.html")
