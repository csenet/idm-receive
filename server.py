import os
import uuid
import time
import random
from datetime import datetime
from typing import Dict, Any
from pathlib import Path
import io
import hashlib
import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont
import requests

app = FastAPI(
    title="IDM Fortune Printer Service",
    description="IDM受信 → AI占い → プリンター出力サービス",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
PRINTER_API_HOST = os.getenv("PRINTER_API_HOST", "http://printer-api:8080")
UPLOAD_DIR = Path("fortune_images")
UPLOAD_DIR.mkdir(exist_ok=True)

idm_mapping = {
    "0140F4FD8927B660": "mcberingi.png"
}

if not OPENROUTER_API_KEY:
    print("警告: OPENROUTER_API_KEYが設定されていません")

try:
    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
    ) if OPENROUTER_API_KEY else None
except Exception as e:
    print(f"OpenAI client initialization error: {e}")
    client = None

fortune_db: Dict[str, Dict[str, Any]] = {}

def get_random_exhibitor() -> str:
    """NT Tokyo APIから日曜日出展者情報をランダムに取得"""
    max_attempts = 10  # 最大試行回数
    
    for attempt in range(max_attempts):
        try:
            # ランダムに出展者IDを生成（1-166の範囲で試す）
            exhibitor_id = random.randint(1, 166)
            api_url = f"https://api.nt-tokyo.org/api/exhibitors/public/by-number/{exhibitor_id}"
            
            print(f"Fetching exhibitor from API (attempt {attempt + 1}): {api_url}")
            response = requests.get(api_url, headers={'accept': 'application/json'}, timeout=5)
            print(f"API response status: {response.status_code}")
            
            if response.status_code == 200:
                exhibitor_data = response.json()
                exhibit_days = exhibitor_data.get('exhibitDays', [])
                exhibitTitle = exhibitor_data.get('exhibitTitle', '')
                
                # sundayが含まれているかチェック
                if 'sunday' in exhibit_days:
                    booth_number = exhibitor_data.get('boothNumber', '')
                    
                    # ブース番号と出展者名を表示
                    if booth_number:
                        return f"{booth_number}の「{exhibitTitle}」をチェックしてみて！"
                    else:
                        return f"出展者{exhibitor_id}番要チェック"
                else:
                    print(f"Exhibitor {exhibitor_id} not exhibiting on Sunday, trying another...")
                    continue
            else:
                print(f"API error for exhibitor {exhibitor_id}, trying another...")
                continue
                
        except Exception as e:
            print(f"Exhibitor API fetch error (attempt {attempt + 1}): {e}")
            continue
    
    # 最大試行回数に達した場合のフォールバック
    print("Could not find Sunday exhibitor after max attempts, using fallback")
    exhibitor_id = random.randint(1, 166)
    return f"出展者{exhibitor_id}番も要チェック"

def generate_fortune(idm_data: str) -> str:
    if not client:
        return "運勢を占うにはAPIキーが必要です"
    
    # ランダムに出展者情報を取得
    exhibitor_info = get_random_exhibitor()
    print(f"Exhibitor info: {exhibitor_info}")
    
    try:
        system_content = "あなたは電子工作やものづくりが好きな占い師です。NT東京での今日の運勢を日本語で楽しく占ってください。必ず「今日のラッキーアイテムは○○！」から始めて、その部品や工具などを使った簡単なアドバイスを含めて、40文字以内で明るく前向きな内容にしてください。"
        
        if exhibitor_info:
            system_content += f" 最後に「{exhibitor_info}」を追加してください。"
        
        completion = client.chat.completions.create(
            extra_headers={
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "IDM Fortune Service",
            },
            model="openai/gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": system_content
                },
                {
                    "role": "user",
                    "content": f"IDMデータ: {idm_data}\n\n今日の運勢を占ってください。"
                }
            ]
        )
        
        return completion.choices[0].message.content
        
    except Exception as e:
        print(f"Fortune generation error: {str(e)}")
        lucky_components = ['LED', 'Arduino', 'Raspberry Pi', 'コンデンサ', 'トランジスタ', 'ブレッドボード', 'IC', '抵抗']
        lucky_component = random.choice(lucky_components)
        result = f"今日のラッキー電子部品は{lucky_component}です！新しいハックのアイデアが浮かびそう。回路作りに良い日になりそうです。"
        if exhibitor_info:
            result += f" {exhibitor_info}"
        return result

def create_card_image(image_filename: str, idm_data: str) -> str:
    """指定されたカード画像を使用して印刷用画像を作成"""
    try:
        card_path = Path("cards") / image_filename
        if not card_path.exists():
            print(f"Card image not found: {card_path}")
            return None
        
        # カード画像を読み込み
        card_img = Image.open(card_path)
        
        # プリンター用サイズに調整
        width = 384
        # 高さはアスペクト比を維持して計算
        height = int(card_img.height * (width / card_img.width))
        
        # 画像をリサイズ
        card_img = card_img.resize((width, height), Image.Resampling.LANCZOS)
        
        filename = f"card_{uuid.uuid4().hex[:8]}.png"
        file_path = UPLOAD_DIR / filename
        card_img.save(file_path, "PNG")
        
        print(f"Card image created: {file_path}")
        return str(file_path)
        
    except Exception as e:
        print(f"Error creating card image: {e}")
        return None

def create_fortune_image(fortune_text: str, idm_data: str) -> str:
    print("=== Starting font loading ===")
    width = 384
    # 高さは後で動的に決定
    temp_img = Image.new('RGB', (width, 100), 'white')
    temp_draw = ImageDraw.Draw(temp_img)
    
    try:
        # Noto Sans CJK フォントを最初に試す（日本語対応）
        title_font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 20)
        text_font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 14)
        small_font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 12)
        print("Successfully loaded Noto Sans CJK Regular fonts")
    except Exception as e:
        print(f"Failed to load Noto Sans CJK Regular: {e}")
        try:
            # Noto Sans CJK ファミリーの別のパスを試す
            title_font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 20)
            text_font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 14)
            small_font = ImageFont.truetype("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 12)
            print("Successfully loaded Noto Sans CJK Bold fonts")
        except Exception as e2:
            print(f"Failed to load Noto Sans CJK Bold: {e2}")
            try:
                # DejaVu フォントにフォールバック
                title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
                text_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
                small_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
                print("Fallback to DejaVu Sans fonts")
            except Exception as e3:
                print(f"All font loading failed, using default: {e3}")
                title_font = ImageFont.load_default()
                text_font = ImageFont.load_default()
                small_font = ImageFont.load_default()
    
    # 絵文字を除去して日本語テキストのみにする
    import re
    clean_text = re.sub(r'[^\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FAF\u3000-\u303Fa-zA-Z0-9。！？、・（）\s]', '', fortune_text)
    
    # 日本語テキストを適切に改行
    lines = []
    max_width = 25  # 1行あたりの文字数をさらに増やす
    current_line = ""
    
    for char in clean_text:
        if char in ['。', '！', '？']:
            current_line += char
            lines.append(current_line.strip())
            current_line = ""
        elif len(current_line) >= max_width:
            lines.append(current_line.strip())
            current_line = char
        else:
            current_line += char
    
    if current_line.strip():
        lines.append(current_line.strip())
    
    print(f"Text lines: {lines}")
    
    # 画像の高さを動的に計算
    y_pos = 10  # 上部余白を削減
    y_pos += 0   # タイトルスペース削除
    y_pos += 30  # ID行
    y_pos += len(lines) * 25  # テキスト行間隔を削減
    y_pos += 20  # 素敵な一日を
    y_pos += 20  # 画像前の間隔を削減
    
    # 画像の高さを事前に計算
    bg_height = 0
    bg_width = 250
    selected_img = None
    background_img = None
    try:
        img_dir = Path("img")
        image_files = list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png"))
        if image_files:
            selected_img = random.choice(image_files)
            background_img = Image.open(selected_img)
            bg_height = int(background_img.height * (bg_width / background_img.width))
    except Exception as e:
        print(f"Error calculating image height: {e}")
        bg_height = 0
    
    # 最終的な画像の高さを決定
    total_height = y_pos + bg_height + 10  # 下部マージンを削減
    
    # 実際の画像を作成
    img = Image.new('RGB', (width, total_height), 'white')
    draw = ImageDraw.Draw(img)
    
    # 画像を一番上に配置
    img_y = 10  # 上部余白最小化
    try:
        if selected_img and background_img and bg_height > 0:
            # 画像をグレースケールに変換
            background_img = background_img.convert('L')  # グレースケール変換
            
            # 画像をリサイズ
            background_img = background_img.resize((bg_width, bg_height), Image.Resampling.LANCZOS)
            
            # 画像を中央に配置
            img_x = (width - bg_width) // 2
            
            # グレースケール画像をペースト
            img.paste(background_img, (img_x, img_y))
            
            print(f"Added grayscale background image at top: {selected_img}, height: {bg_height}")
        else:
            print(f"No image to add - selected_img: {selected_img}, bg_height: {bg_height}")
    except Exception as e:
        print(f"Error adding background image: {e}")
        import traceback
        print(traceback.format_exc())
    
    # コンテンツを画像の下に配置
    y_pos = img_y + bg_height + 15  # 画像の下、間隔を削減
    
    draw.text((10, y_pos), f"IDM: {idm_data}", font=small_font, fill='black', anchor='lt')
    y_pos += 30  # ID行の間隔を削減
    
    for line in lines:
        draw.text((10, y_pos), line, font=text_font, fill='black', anchor='lt')
        y_pos += 25  # テキスト行間隔を削減
    
    filename = f"fortune_{uuid.uuid4().hex[:8]}.png"
    file_path = UPLOAD_DIR / filename
    img.save(file_path, "PNG")
    
    return str(file_path)

def send_to_printer(image_path: str) -> bool:
    try:
        with open(image_path, "rb") as f:
            files = {"imgf": (os.path.basename(image_path), f, "image/png")}

            print(f"Sending to printer: {PRINTER_API_HOST}")
            response = requests.post(f"{PRINTER_API_HOST}", files=files, timeout=30)
            
            if response.status_code == 200:
                print("Print job completed successfully")
                return True
            else:
                print(f"Printer API error: {response.status_code}, {response.text}")
                return False
                
    except Exception as e:
        print(f"Printer connection error: {str(e)}")
        return False

@app.post("/idm")
async def receive_idm(request: Request):
    try:
        timestamp = datetime.now().isoformat()
        
        # リクエストボディをテキストとして取得
        idm_data = await request.body()
        idm_text = idm_data.decode('utf-8').strip()
        
        # IDMテキストをIDとして使用
        idm_id = idm_text
        
        print(f"[{timestamp}] IDM受信: {idm_text}")
        
        # idm_mappingをチェックしてカード画像が指定されているか確認
        if idm_id in idm_mapping:
            card_filename = idm_mapping[idm_id]
            print(f"カード画像が指定されています: {card_filename}")
            
            # カード画像を作成
            card_image_path = create_card_image(card_filename, idm_id)
            if card_image_path:
                print_success = send_to_printer(card_image_path)
                
                return {
                    "status": "success",
                    "message": "Card image sent to printer" if print_success else "Card image generated but print failed",
                    "idm_id": idm_id,
                    "card_filename": card_filename,
                    "image_path": card_image_path,
                    "print_success": print_success,
                    "timestamp": timestamp,
                    "type": "card"
                }
        
        
        fortune_text = generate_fortune(idm_text)
        print(f"生成された占い: {fortune_text}")
        
        image_path = create_fortune_image(fortune_text, idm_id)
        print(f"画像作成完了: {image_path}")
        
        print_success = send_to_printer(image_path)
        
        return {
            "status": "success",
            "message": "Fortune generated and sent to printer" if print_success else "Fortune generated but print failed",
            "idm_id": idm_id,
            "fortune": fortune_text,
            "image_path": image_path,
            "print_success": print_success,
            "timestamp": timestamp
        }
        
    except Exception as e:
        print(f"エラー: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/fortune/{idm_id}")
async def get_fortune(idm_id: str):
    if idm_id not in fortune_db:
        raise HTTPException(status_code=404, detail="Fortune not found")
    
    return fortune_db[idm_id]

@app.get("/health")
async def health_check():
    return {"status": "OK", "openrouter_configured": OPENROUTER_API_KEY is not None}

@app.get("/")
async def root():
    return {
        "service": "IDM Fortune Printer Service",
        "version": "1.0.0",
        "status": "ready",
        "endpoints": {
            "idm": "POST /idm - IDMデータを受信して占い・印刷",
            "fortune": "GET /fortune/{idm_id} - 占い結果を取得",
            "health": "GET /health - ヘルスチェック"
        }
    }

if __name__ == "__main__":
    import uvicorn
    print("IDM占い・プリンターサービスを開始します...")
    uvicorn.run(app, host="0.0.0.0", port=8888)
