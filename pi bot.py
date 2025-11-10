# -*- coding: utf-8 -*-
import os, time, math, threading, requests
from PIL import Image, ImageDraw
import st7789
from telegram.ext import Updater, MessageHandler, Filters
from telegram import Bot

os.environ['GPIOZERO_PIN_FACTORY'] = 'lgpio'
from gpiozero import Servo, Button

BOT_TOKEN = "Token?"
PC_SERVER = "?"
MY_ID = id telegram
VOICE_SPEED = 0.9
USE_JAPANESE = False

servo = Servo(18)
servo.value = None
touch = Button(23, bounce_time=0.1, pull_up=True)

W, H = 320, 240
FPS = 30

BEAR_BROWN = (185, 142, 97)
EYE_BLACK = (25, 25, 25)
EYE_GLOW = (255, 255, 255)
MOUTH_RED = (180, 50, 60)
CHEEK_NEUTRAL = (255, 180, 180)

MOOD_CHEEKS = {
    "happy": (255, 160, 170),
    "love": (255, 120, 150),
    "shy": (255, 140, 160),
    "sad": (160, 180, 255),
    "angry": (255, 120, 120),
    "neutral": CHEEK_NEUTRAL,
}

MOOD_KEYWORDS = {
    "love": ["i love you", "love you", "miss you", "miss u", "愛してる", "大好き", "会いたい"],
    "shy": ["shy", "blush", "embarrassed", "恥ずかしい", "照れる"],
    "happy": ["happy", "good", "great", "awesome", "amazing", "yay", "嬉しい", "楽しい", "最高"],
    "sad": ["sad", "lonely", "cry", "crying", "miss", "悲しい", "寂しい", "泣"],
    "angry": ["angry", "mad", "annoyed", "upset", "怒", "むかつく", "腹立つ"],
}

class BearFace:
    def __init__(self):
        self.disp = st7789.ST7789(
            width=W, height=H, rotation=0, port=0, cs=1, dc=9,
            backlight=13, spi_speed_hz=80_000_000
        )
        self.mood = "neutral"
        self.mood_until = 0
        self.is_speaking = False
        self.mouth_phase = 0.0
        self.blink_state = 1.0
        self.running = True
        threading.Thread(target=self.loop, daemon=True).start()

    def draw(self, mouth_open=0.0):
        cheek_color = MOOD_CHEEKS.get(self.mood, CHEEK_NEUTRAL)
        img = Image.new("RGB", (W, H), BEAR_BROWN)
        d = ImageDraw.Draw(img)

        d.ellipse((12, 4, 92, 84), fill=BEAR_BROWN)
        d.ellipse((W-92, 4, W-12, 84), fill=BEAR_BROWN)

        left_x, right_x, eye_y = 110, 200, 110
        eye_w, eye_h = 40, int(40 * self.blink_state)
        d.ellipse((left_x-eye_w, eye_y-eye_h, left_x+eye_w, eye_y+eye_h), fill=EYE_BLACK)
        d.ellipse((right_x-eye_w, eye_y-eye_h, right_x+eye_w, eye_y+eye_h), fill=EYE_BLACK)

        if self.blink_state > 0.5:
            d.ellipse((left_x-6, eye_y-6, left_x, eye_y), fill=EYE_GLOW)
            d.ellipse((right_x-6, eye_y-6, right_x, eye_y), fill=EYE_GLOW)

        d.ellipse((150, 120, 170, 135), fill=EYE_BLACK)

        open_amt = int(8 + 10 * mouth_open)
        if open_amt > 2:
            d.rectangle((145, 160, 175, 160+open_amt), fill=MOUTH_RED)
        else:
            d.line((145, 165, 175, 165), fill=EYE_BLACK, width=3)

        if self.mood == "love":
            self.draw_heart(d, 105, 150, 15, (255, 120, 150))
            self.draw_heart(d, 215, 150, 15, (255, 120, 150))
        elif self.mood == "sad":
            self.draw_tear(d, 105, 150, (120, 160, 255))
            self.draw_tear(d, 215, 150, (120, 160, 255))
        else:
            d.ellipse((90, 135, 120, 165), fill=cheek_color)
            d.ellipse((200, 135, 230, 165), fill=cheek_color)
        
        if self.mood == "angry":
            overlay = Image.new("RGBA", (W, H), (255, 80, 80, 60))
            img.paste(overlay, (0, 0), overlay)

        self.disp.display(img)
    
    def draw_heart(self, draw, cx, cy, size, color):
        draw.ellipse((cx-size, cy-size//2, cx, cy+size//2), fill=color)
        draw.ellipse((cx, cy-size//2, cx+size, cy+size//2), fill=color)
        points = [(cx-size, cy), (cx+size, cy), (cx, cy+size*1.3)]
        draw.polygon(points, fill=color)
    
    def draw_tear(self, draw, cx, cy, color):
        draw.ellipse((cx-8, cy-5, cx+8, cy+11), fill=color)
        points = [(cx-8, cy+3), (cx+8, cy+3), (cx, cy+25)]
        draw.polygon(points, fill=color)

    def set_mood(self, mood, duration=5):
        self.mood = mood
        self.mood_until = time.time() + duration

    def set_speaking(self, state):
        self.is_speaking = state

    def loop(self):
        while self.running:
            t = time.time() % 5
            if t < 0.1:
                self.blink_state = 0.1
            elif t < 0.2:
                self.blink_state = 0.4
            elif t < 0.25:
                self.blink_state = 1.0
            else:
                self.blink_state = 1.0

            if self.is_speaking:
                self.mouth_phase += 0.3
                mouth_open = (math.sin(self.mouth_phase) + 1) / 2
            else:
                self.mouth_phase = 0
                mouth_open = 0.0

            if self.mood != "neutral" and time.time() > self.mood_until:
                self.mood = "neutral"

            self.draw(mouth_open)
            time.sleep(1 / FPS)

def smooth_move(start, end, duration=0.3, steps=20):
    for i in range(steps):
        progress = i / (steps - 1)
        eased = progress * progress * (3.0 - 2.0 * progress)
        value = start + (end - start) * eased
        servo.value = value
        time.sleep(duration / steps)

def shake_head_no():
    print("Shaking head gently (no)")
    servo.value = 0
    time.sleep(0.2)
    for _ in range(2):
        smooth_move(0, -0.3, 0.25, 20)
        smooth_move(-0.3, 0.3, 0.25, 20)
    smooth_move(0.3, 0, 0.2, 15)
    time.sleep(0.2)
    servo.value = None

def shake_head_poke():
    print("Shaking head slowly (poke)")
    servo.value = 0
    time.sleep(0.2)
    for _ in range(2):
        smooth_move(0, -0.25, 0.4, 25)
        smooth_move(-0.25, 0.25, 0.4, 25)
    smooth_move(0.25, 0, 0.3, 20)
    time.sleep(0.2)
    servo.value = None

def detect_language(text):
    japanese_chars = sum(1 for c in text if '\u3040' <= c <= '\u309F' or '\u30A0' <= c <= '\u30FF' or '\u4E00' <= c <= '\u9FFF')
    if len(text) > 0 and japanese_chars / len(text) > 0.3:
        return "ja"
    return "en"

def detect_mood(text):
    t = text.lower()
    for mood, keys in MOOD_KEYWORDS.items():
        for k in keys:
            if k in t:
                return mood
    return "neutral"

def speak_clone(text, display, mood, should_shake=False):
    language = "ja" if USE_JAPANESE else detect_language(text)
    payload = {"text": text, "speaker": "default", "speed": VOICE_SPEED, "language": language}
    try:
        r = requests.post(PC_SERVER, json=payload, timeout=15)
        if r.status_code != 200:
            print(f"TTS error: {r.status_code}")
            return
        with open("voice.mp3", "wb") as f:
            f.write(r.content)
        os.system("ffmpeg -y -i voice.mp3 -ar 22050 -ac 1 -acodec pcm_s16le fixed.wav >/dev/null 2>&1")
        display.set_mood(mood, 5)
        display.set_speaking(True)
        if should_shake:
            threading.Thread(target=shake_head_no, daemon=True).start()
        os.system("aplay fixed.wav >/dev/null 2>&1")
    except requests.exceptions.Timeout:
        print("TTS server timeout")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        display.set_speaking(False)

last_poke_time = 0

def on_touch_pressed(bot):
    global last_poke_time
    current_time = time.time()
    if current_time - last_poke_time < 1.0:
        return
    last_poke_time = current_time
    print("Touch detected! Sending poke message")
    threading.Thread(target=shake_head_poke, daemon=True).start()
    def send_message():
        try:
            bot.send_message(chat_id=MY_ID, text="You got poked 💕")
            print("Poke message sent!")
        except Exception as e:
            print(f"Error sending poke: {e}")
    threading.Thread(target=send_message, daemon=True).start()

def handle(update, context, display):
    text = update.message.text
    uid = update.message.from_user.id
    if uid == MY_ID:
        mood = detect_mood(text)
        text_lower = text.lower()
        should_shake = "nope" in text_lower or " no " in text_lower or text_lower.startswith("no ") or text_lower.endswith(" no")
        speak_clone(text, display, mood, should_shake)

def main():
    display = BearFace()
    bot = Bot(token=BOT_TOKEN)
    touch.when_pressed = lambda: on_touch_pressed(bot)
    print("Bot Start")
    print("=" * 50)
    print("Ready to receive your messages!")
    print("=" * 50)
    updater = Updater(BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, lambda u, c: handle(u, c, display)))
    updater.start_polling()
    updater.idle()

if __name__ == "__main__":
    main()
