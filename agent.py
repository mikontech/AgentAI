import base64
import datetime as dt
import hashlib
import html
import json
import os
import random
import re
from pathlib import Path
from urllib.parse import quote

import feedparser
import requests

ROOT = Path(__file__).resolve().parent
DOCS = ROOT / 'docs'
DATA = ROOT / 'data'
TIMEOUT = 75


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except FileNotFoundError:
        return default


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def fetch_news(queries):
    news = []
    for query in queries[:3]:
        url = 'https://news.google.com/rss/search?q=' + quote(query + ' when:14d') + '&hl=pl&gl=PL&ceid=PL:pl'
        try:
            response = requests.get(url, headers={'User-Agent': 'Mozilla/5.0 (MonitoringContentAgent/1.0)'}, timeout=20)
            response.raise_for_status()
            feed = feedparser.parse(response.content)
            for entry in feed.entries[:5]:
                title = re.sub(r'<[^>]+>', '', entry.get('title', '')).strip()
                link = entry.get('link', '')
                published = entry.get('published', '')
                if title and link and not any(item['link'] == link for item in news):
                    news.append({'title': title[:220], 'link': link, 'published': published[:90]})
        except Exception as exc:
            print(f'RSS niedostępny dla {query}: {exc}')
    return news[:12]


def choose_question(config, history):
    questions = config.get('customer_questions', [])
    if not questions:
        raise ValueError('W config.json dodaj przynajmniej jedno pytanie klienta')
    used = {p.get('question') for p in history[-len(questions):]}
    remaining = [q for q in questions if q not in used] or questions
    return random.choice(remaining)


def generate_post(config, question, news, previous):
    key = os.environ['GROQ_API_KEY']
    today = dt.date.today().isoformat()
    news_context = '\n'.join(f'- {x["title"]} ({x["published"]}); źródło: {x["link"]}' for x in news)
    recent = '\n'.join(p.get('title', '') for p in previous[-8:])
    system = ('Jesteś polskim ekspertem ds. marketingu firmy instalującej monitoring CCTV. '
              'Twórz autentyczne, użyteczne, poprawne technicznie materiały. '
              'Nie wymyślaj cen, statystyk, norm prawnych ani informacji o produktach. '
              'Nie powielaj plotek ani niepotwierdzonych trendów. '
              'Wskazówki prawne traktuj ogólnie, bez przedstawiania ich jako porady prawnej. '
              'Nie strasz przestępczością. Nie twierdź, że kamery zapewniają 100% bezpieczeństwa. '
              'Odpowiadaj wyłącznie czystym obiektem JSON bez bloków markdown.')
    prompt = f'''Data: {today}
Firma: {config['company_name']}, lokalizacja: {config['city']}
Usługi: {', '.join(config['services'])}
Odbiorcy: {config['audience']}
Styl: {config['tone']}
Wezwanie do działania: {config['cta']}
Pytanie klienta, które post ma konkretnie rozwiązać: {question}
Nagłówki aktualności (mogą być niepowiązane albo niewiarygodne, NIE uznawaj ich automatycznie za fakty):
{news_context or 'Brak aktualnych wiadomości; oprzyj się na ponadczasowych poradach.'}
Ostatnie nagłówki, których nie należy powtarzać:
{recent or 'brak'}
Zadanie: stwórz JEDEN atrakcyjny post Facebook/Instagram, 500-900 znaków w języku polskim, z konkretną odpowiedzią na pytanie, naturalnym CTA, maksymalnie 4 hashtagami. Nawiąż do trendu tylko jeśli jest naprawdę adekwatny; w razie braku wiarygodnego związku wybierz ponadczasowy temat. Unikaj obietnic i faktów niepopartych danymi. Grafika ma ilustrować temat bez tekstu i logo, w proporcji 4:3, realistycznie, estetycznie, z technicznie wiarygodną kamerą.
Zwróć JSON z polami: "title" (krótko), "post" (gotowy tekst z hashtagami), "image_prompt" (szczegółowy prompt po angielsku bez napisów), "trend_note" (1 zdanie w języku polskim czy i jak użyto trendu), "source_urls" (lista maksymalnie 2 linków z podanych wyżej, tylko jeśli rzeczywiście stanowiły inspirację).'''
    r = requests.post('https://api.groq.com/openai/v1/chat/completions',
        headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'},
        json={'model': config.get('groq_model', 'llama-3.3-70b-versatile'), 'temperature': 0.65,
              'response_format': {'type': 'json_object'},
              'messages': [{'role': 'system', 'content': system}, {'role': 'user', 'content': prompt}]}, timeout=TIMEOUT)
    
    print("Model Groq:", config.get("groq_model"))
    print("Status Groq:", r.status_code)

    if not r.ok:
        print("Odpowiedź Groq:", r.text[:1500])
        r.raise_for_status()

    content = r.json()['choices'][0]['message']['content']
    data = json.loads(content)
    if not all(isinstance(data.get(k), str) and data[k].strip() for k in ['title','post','image_prompt']):
        raise ValueError('Model Groq zwrócił niekompletną treść')
    valid = {n['link'] for n in news}
    data['source_urls'] = [u for u in data.get('source_urls', []) if isinstance(u, str) and u in valid][:2]
    return data


def generate_image(prompt, slug):
    account_id = os.environ['CLOUDFLARE_ACCOUNT_ID']
    token = os.environ['CLOUDFLARE_API_TOKEN']
    url = f'https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/black-forest-labs/flux-1-schnell'
    
    request_payload = {
        'prompt': (prompt + ', no text, no letters, no watermark, no logo')[:2048],
        'steps': 4
    }

    r = requests.post(url, headers={'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'},
                      json=request_payload, timeout=120)
    
    if not r.ok:
        print("Cloudflare status:", r.status_code)
        print("Cloudflare odpowiedź:", r.text[:1500])
        r.raise_for_status()

    blob = r.json()
    if not blob.get('success', False) or not blob.get('result', {}).get('image'):
        raise RuntimeError(f'Cloudflare nie zwrócił grafiki: {str(blob)[:350]}')
    raw = base64.b64decode(blob['result']['image'])
    if len(raw) < 1000:
        raise RuntimeError('Zwrócona grafika jest nieprawidłowa')
    path = DOCS / 'images' / f'{slug}.jpg'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return f'images/{slug}.jpg'


def esc(value):
    return html.escape(str(value), quote=True)


def render(posts, company):
    cards = []
    for post in reversed(posts):
        image = f'<img loading="lazy" alt="Grafika AI do posta" src="{esc(post["image"])}">' if post.get('image') else '<div class="missing">Nie wygenerowano grafiki — sprawdź log uruchomienia.</div>'
        sources = ''.join(f'<a href="{esc(u)}" target="_blank" rel="noopener noreferrer">Źródło {i+1}</a> ' for i,u in enumerate(post.get('source_urls', [])))
        download = f'<a class="btn" download href="{esc(post["image"])}">Pobierz grafikę</a>' if post.get('image') else ''
        cards.append(f'''<article class="card"><div class="art">{image}</div><div class="content"><p class="date">{esc(post['date'])} · Propozycja do akceptacji</p><h2>{esc(post['title'])}</h2><p class="question"><strong>Pytanie klienta:</strong> {esc(post['question'])}</p><div class="post">{esc(post['post'])}</div><p class="note">{esc(post.get('trend_note',''))}</p><div class="sources">{sources}</div><div class="actions"><button type="button" class="btn copy" data-post="{esc(post['id'])}">Kopiuj tekst posta</button>{download}</div></div></article>''')
    css = '''*{box-sizing:border-box}body{margin:0;background:#f4f6fa;color:#172334;font:16px/1.6 system-ui,-apple-system,Segoe UI,sans-serif}header{background:linear-gradient(120deg,#0e2541,#174d70);color:white;padding:48px max(22px,calc((100vw - 1080px)/2))}h1{font-size:clamp(28px,5vw,42px);line-height:1.15;margin:4px 0 8px}header p{opacity:.85;max-width:640px}main{max-width:1080px;margin:32px auto;padding:0 20px}.card{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.2fr);background:white;border:1px solid #e1e7ed;border-radius:18px;overflow:hidden;margin-bottom:25px;box-shadow:0 8px 25px #1428440b}.art{background:#dae5eb;min-height:290px}.art img{width:100%;height:100%;min-height:290px;object-fit:cover;display:block}.content{padding:28px}.date{color:#557184;font-size:13px;font-weight:700;text-transform:uppercase;letter-spacing:.03em;margin:0}.content h2{line-height:1.25;margin:8px 0 18px}.question{font-size:14px;background:#edf6fb;padding:10px 14px;border-radius:8px}.post{white-space:pre-wrap;line-height:1.65}.note{color:#526a7b;font-size:14px}.sources{font-size:13px}.sources a{color:#07608d;margin-right:10px}.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px}.btn{border:0;background:#0c5477;color:white;font:600 14px system-ui;padding:12px 16px;border-radius:9px;cursor:pointer;text-decoration:none;display:inline-block}.btn:hover{background:#093e59}.missing{padding:22px;color:#6b3e21}.footer{color:#7b8790;text-align:center;margin:30px auto 50px;font-size:13px}@media(max-width:730px){.card{grid-template-columns:1fr}.art,.art img{min-height:200px}.content{padding:20px}}'''
    data_json = json.dumps({p['id']: p['post'] for p in posts}, ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    document = f'''<!doctype html><html lang="pl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Propozycje postów — {esc(company)}</title><style>{css}</style></head><body><header><div class="eyebrow">ASYSTENT MARKETINGOWY AI</div><h1>Propozycje postów</h1><p>{esc(company)} · Nowe propozycje w poniedziałki, środy i piątki. Każdą treść i grafikę sprawdź przed publikacją.</p></header><main>{''.join(cards) or '<p>Brak propozycji. Uruchom agenta w GitHub Actions.</p>'}</main><p class="footer">Treści i grafiki tworzone przez AI. Posty nie są automatycznie publikowane.</p><script type="application/json" id="posts-data">{data_json}</script><script>const POSTS=JSON.parse(document.getElementById('posts-data').textContent);document.querySelectorAll('.copy').forEach(b=>b.addEventListener('click',async()=>{{try{{await navigator.clipboard.writeText(POSTS[b.dataset.post]);b.textContent='Skopiowano!';setTimeout(()=>b.textContent='Kopiuj tekst posta',2000)}}catch(e){{alert('Nie udało się skopiować. Zaznacz tekst ręcznie.')}}}}));</script></body></html>'''
    (DOCS / 'index.html').write_text(document, encoding='utf-8')


def main():
    config = load_json(ROOT / 'config.json', {})
    history = load_json(DATA / 'posts.json', [])
    date = dt.date.today().isoformat()
    
    if any(p.get('date') == date for p in history) and os.getenv('FORCE_NEW') != '1':
        for post in history:
            if post.get('date') == date and not post.get('image'):
                print('Ponawiam generowanie brakującej grafiki...')
                try:
                    post['image'] = generate_image(
                        post['image_prompt'], post['id']
                    )
                    print('Grafika zapisana:', post['image'])
                except Exception as exc:
                    print('Błąd ponownej próby:', exc)
                    raise

        save_json(DATA / 'posts.json', history)
        render(history, config.get('company_name', 'Firma monitoringowa'))
        return

    question = choose_question(config, history)
    news = fetch_news(config.get('news_queries', []))
    content = generate_post(config, question, news, history)
    slug = date + '-' + hashlib.sha1((question + str(random.random())).encode()).hexdigest()[:8]
    # Zapisz treść także przy chwilowym błędzie API grafiki, aby łatwo ponowić.
    try:
        image = generate_image(content['image_prompt'], slug)
    except Exception as exc:
        print(f'UWAGA: błąd generowania grafiki: {exc}')
        image = ''
    post = {'id': slug, 'date': date, 'question': question, 'title': content['title'],
            'post': content['post'], 'image_prompt': content['image_prompt'],
            'image': image, 'trend_note': content.get('trend_note',''),
            'source_urls': content.get('source_urls', [])}
    history.append(post)
    history = history[-48:]
    save_json(DATA / 'posts.json', history)
    render(history, config.get('company_name', 'Firma monitoringowa'))
    print('Utworzono propozycję:', post['title'], 'grafika:', image or 'BRAK')


if __name__ == '__main__':
    main()
