"""Choose a voice and an emotion for each sentence using simple rules (no AI model needed).

The gender comes from speech style only (俺, ぼく, だぜ, わよ, ...). The emotion comes from keywords and punctuation.
When unsure, the emotion is neutral and the voice is picked pseudo-randomly from the note id.
"""
import re
import zlib

EMOTIONS = ["neutral", "happy", "sad", "angry", "scared", "whisper", "joking"]

MALE = re.compile(
    r"(?:じゃあ?|く|ん)ねえ|ねえ[よぞなだ]|ねぇ|だろうな|のじゃ|じゃ[。！!…]*$|だからな|てしまったな|"
    r"俺|おれ|オレ|僕|ぼく|ボク|わし|儂|だぜ|ぜ[！!。…]*$|だぞ|ぞ[！!。…]*$|てめえ|おめえ|お前|おまえ|"
    r"だな[。！!]*$|ぞ！|じゃねえ|ねえよ|やがる|してやる"
)
FEMALE = re.compile(
    r"あたし|あたくし|わたくし|わよ|のよ|かしら|だわ[ねよ！!。…]*$|わね|のね|"
    r"わ[！!。…]*$|でしょ[うっ]?[！!。]*$|なのよ|ちゃん"
)

EMOTION_RULES = [
    ("whisper", re.compile(r"^[（(].*[）)]$")),
    ("scared", re.compile(r"怖|こわ|助けて|たすけて|やめて|ひい|嫌[だっ]|来ないで|ヤバい?とりあえず|死ぬ|殺され")),
    ("angry", re.compile(r"てめえ|ふざけ|許さ|うるさ|黙れ|バカ|馬鹿|くそ|クソ|ぶっ殺|ぶっ飛ばし|腹立|ムカつ|怒")),
    ("sad", re.compile(r"悲し|寂し|さみし|泣|辛い|つらい|ごめん|会いたい|別れ|死んじゃ|いなくなっ|ううっ|うぅ")),
    ("joking", re.compile(r"あはは|ははは|フフ|ハハ|あはっ|うふふ|ふふ|えへへ|笑っ?ちゃ|冗談|なんてね|www|ｗ|なんちゃって")),
    ("happy", re.compile(r"やった|嬉し|うれし|楽しい|楽しみ|ありがとう|大好き|最高|わーい|よかった|素敵")),
]

PREFERRED = {
    "happy": ("female_bright", "male_young"),
    "joking": ("female_bright", "male_young"),
    "angry": ("female_cool", "male_deep"),
    "sad": ("female_calm", "male_calm"),
    "whisper": ("female_calm", "male_calm"),
}


def _hash(s):
    return zlib.crc32(s.encode("utf-8"))


def rule_gender(text):
    m = 2 if MALE.search(text) else 0
    f = 2 if FEMALE.search(text) else 0
    if m > f:
        return "m"
    if f > m:
        return "f"
    return None


def rule_emotion(text):
    for emotion, pattern in EMOTION_RULES:
        if pattern.search(text):
            return emotion
    return "neutral"


def pick_voice(voices, gender, emotion, key):
    pool = [k for k, v in voices.items() if gender is None or v["gender"] == gender]
    cands = pool
    pref = PREFERRED.get(emotion)
    if pref:
        p = [k for k in pool if k in pref]
        if p and _hash(key) % 3 != 0:
            cands = p
    return cands[_hash(key + "v") % len(cands)]


def make_plan(cfg, text, key):
    """Return the voice id, emotion, caption and the text to send to the model. The note itself is never changed."""
    voices = cfg["VOICES"]
    gender = rule_gender(text)
    emotion = rule_emotion(text)
    name = pick_voice(voices, gender, emotion, key)
    wrap = cfg["EMOTION_TEXT_WRAP"].get(emotion)
    sent = (wrap[0] + text + wrap[1]) if wrap else text
    return {
        "voice_name": name,
        "voice": voices[name]["voice"],
        "gender": gender,
        "emotion": emotion,
        "caption": cfg["EMOTION_CAPTIONS"].get(emotion, ""),
        "text": sent,
    }
