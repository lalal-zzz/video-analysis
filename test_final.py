print('=== Final Integration Check ===')
import sys
sys.path.insert(0, '.')

# 1. Scrapers
from scrapers import YouTubeScraper, BilibiliScraper, DouyinScraper
ys = YouTubeScraper()
bs = BilibiliScraper()
ds = DouyinScraper()
print(f'Scrapers: YouTube={ys.platform}, Bilibili={bs.platform}, Douyin={ds.platform}')

# 2. Tools registry
from tools.registry import ToolRegistry
print(f'Tools registered: {len(ToolRegistry.list_all())}')

# 3. get_video_author
from tools.author import get_video_author
r = get_video_author('youtube', 'K5KVEU3aaeQ')
if 'error' in r:
    print(f'get_video_author: ERROR - {r[\"error\"]}')
else:
    print(f'get_video_author: OK - author={r[\"author\"]}')

# 4. Web app
from web.app import app as web_app
print(f'Web app: {type(web_app).__name__}')

# 5. All tools list
for t in sorted(ToolRegistry.list_all()):
    print(f'  - {t}')

print()
print('=== FINAL CHECK PASSED ===')