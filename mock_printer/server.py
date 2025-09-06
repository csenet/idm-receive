from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
import time
import random

app = FastAPI(
    title="Mock Printer API",
    description="Mock printer service for testing",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/0")
@app.post("/1")
async def print_image(imgf: UploadFile = File(...)):
    # ランダムな印刷遅延をシミュレート
    delay = random.uniform(0.5, 2.0)
    time.sleep(delay)
    
    file_content = await imgf.read()
    
    print(f"[MOCK PRINTER] 受信: {imgf.filename}, サイズ: {len(file_content)} bytes")
    print(f"[MOCK PRINTER] 印刷処理時間: {delay:.2f}秒")
    
    # 90%の確率で成功
    if random.random() < 0.9:
        print("[MOCK PRINTER] 印刷成功!")
        return {"status": "success", "message": "Print job completed"}
    else:
        print("[MOCK PRINTER] 印刷エラー (mock)")
        return {"status": "error", "message": "Mock printer error"}, 500

@app.get("/")
async def root():
    return {"service": "Mock Printer API", "status": "ready"}

@app.get("/health")
async def health():
    return {"status": "OK"}

if __name__ == "__main__":
    import uvicorn
    print("Mock Printer API開始...")
    uvicorn.run(app, host="0.0.0.0", port=8080)