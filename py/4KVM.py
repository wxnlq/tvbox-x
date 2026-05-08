# coding=utf-8
"""
目标站: 4KVM  首页: https://www.4kvm.net
功能: 动态筛选、精准分集、多线路、播放链接解析
"""
import re
import sys
import json
import urllib.parse
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    def init(self, extend=""):
        self.site_url = "https://www.4kvm.net"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': self.site_url,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8'
        }
        self.categories = [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "电视剧"},
            {"type_id": "3", "type_name": "动漫"}
        ]
        self._filters_cache = None

    # ---------- 辅助方法 ----------
    def _fetch_html(self, path, params=None):
        """请求页面并返回BeautifulSoup对象，失败返回None"""
        url = path if path.startswith('http') else self.site_url + path
        if params:
            query = urllib.parse.urlencode(params)
            url = f"{url}?{query}" if '?' not in url else f"{url}&{query}"
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return None
        return BeautifulSoup(resp.text, 'html.parser')

    def _extract_video_card(self, card):
        """从卡片div[data-vod-id]中提取视频信息"""
        a = card.select_one('a.block[href^="/play/"]')
        if not a:
            return None
        vod_id = card.get('data-vod-id', '').strip()
        if not vod_id:
            href = a.get('href', '')
            vod_id = href.replace('/play/', '').strip()
        if not vod_id:
            return None
        title_tag = card.select_one('h3.text-white') or card.select_one('h3')
        vod_name = title_tag.get_text(strip=True) if title_tag else ''
        if not vod_name:
            return None
        img = card.select_one('img[data-src]')
        vod_pic = ''
        if img:
            src = img.get('data-src', '')
            if src and not src.startswith('data:'):
                vod_pic = src if src.startswith('http') else 'https:' + src
        remark_tag = card.select_one('.text-green-500, .text-yellow-400, span[class*="px-1.5"]')
        vod_remarks = remark_tag.get_text(strip=True) if remark_tag else ''
        return {
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_remarks": vod_remarks
        }

    def _extract_video_list(self, soup):
        cards = soup.select('div[data-vod-id]')
        videos = []
        for card in cards:
            v = self._extract_video_card(card)
            if v:
                videos.append(v)
        return videos

    # ---------- 动态筛选 ----------
    def _fetch_filters_for_classify(self, tid):
        soup = self._fetch_html('/filter', params={'classify': tid})
        if not soup:
            return []
        filter_groups = []
        containers = soup.select('main div.flex.flex-wrap.items-center.gap-3')
        for container in containers:
            links = container.select('a[href]')
            if len(links) < 2:
                continue
            first_text = links[0].get_text(strip=True)
            if not first_text.startswith('全部'):
                continue
            group_name = first_text.replace('全部', '', 1).strip()
            param_key = None
            for a in links[1:]:
                href = a.get('href', '')
                parsed = urllib.parse.urlparse(href)
                qs = urllib.parse.parse_qs(parsed.query)
                for k in qs:
                    if k not in ('classify', 'page'):
                        param_key = k
                        break
                if param_key:
                    break
            if not param_key or param_key in ('sort_by', 'order'):
                continue
            options = []
            for a in links:
                text = a.get_text(strip=True)
                href = a.get('href', '')
                parsed = urllib.parse.urlparse(href)
                qs = urllib.parse.parse_qs(parsed.query)
                val = qs.get(param_key, [''])[0] if param_key in qs else ''
                if text.startswith('全部'):
                    val = ''
                options.append({"n": text, "v": val})
            if options:
                filter_groups.append({
                    "key": param_key,
                    "name": group_name,
                    "value": options
                })
        return filter_groups

    def _get_all_filters(self):
        if self._filters_cache is not None:
            return self._filters_cache
        filters = {}
        for cat in self.categories:
            tid = cat["type_id"]
            groups = self._fetch_filters_for_classify(tid)
            if groups:
                filters[tid] = groups
        if "1" in filters:
            for cid in ["3", "4"]:
                if cid not in filters:
                    filters[cid] = filters["1"]
        self._filters_cache = filters
        return filters

    # ---------- 首页 ----------
    def homeContent(self, filter):
        soup = self._fetch_html('/')
        video_list = []
        if soup:
            video_list = self._extract_video_list(soup)[:20]
        return {
            "class": self.categories,
            "list": video_list,
            "filters": self._get_all_filters()
        }

    def homeVideoContent(self):
        return self.homeContent(False)

    # ---------- 分类页 ----------
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        params = {"classify": tid}
        if extend:
            for k, v in extend.items():
                if v and k != 'classify':
                    params[k] = v
        if page > 1:
            params['page'] = page

        soup = self._fetch_html('/filter', params=params)
        if not soup:
            return {"list": [], "page": page, "pagecount": 1, "limit": 24, "total": 0}

        video_list = self._extract_video_list(soup)

        # 解析总页数
        pagecount = page
        page_text = soup.find(string=re.compile(r'共\s*\d+\s*页'))
        if page_text:
            nums = re.findall(r'\d+', page_text)
            if nums:
                pagecount = int(nums[-1])
        else:
            page_block = soup.select_one('.flex.justify-center')
            if page_block:
                page_links = page_block.select('a[href*="page="]')
                for a in page_links:
                    text = a.get_text(strip=True)
                    if text.isdigit():
                        pagecount = max(pagecount, int(text))
        return {
            "list": video_list,
            "page": page,
            "pagecount": pagecount,
            "limit": 24,
            "total": len(video_list) * pagecount
        }

    # ---------- 详情页 ----------
    def detailContent(self, ids):
        if not ids:
            return {"list": []}
        vod_id = ids[0]
        soup = self._fetch_html(f'/play/{vod_id}')
        if not soup:
            return {"list": []}

        # 标题
        title_elem = soup.select_one('h1.text-xl') or soup.select_one('h1') or soup.select_one('h2')
        vod_name = title_elem.get_text(strip=True) if title_elem else vod_id

        # 图片
        vod_pic = ''
        img_elem = soup.select_one('img.w-full') or soup.select_one('img[src]')
        if img_elem:
            src = img_elem.get('src', '') or img_elem.get('data-src', '')
            if src and not src.startswith('data:'):
                vod_pic = src if src.startswith('http') else 'https:' + src

        # 导演、演员、简介
        vod_director = ''
        vod_actor = ''
        vod_content = ''
        info_block = soup.select_one('.rounded-lg div.grid') or soup.select_one('div.grid')
        if info_block:
            text = info_block.get_text(' ', strip=True)
            dir_match = re.search(r'导演\s*([^主\n]+)', text)
            if dir_match:
                vod_director = dir_match.group(1).strip()
            act_match = re.search(r'主演\s*([^剧\n]+)', text)
            if act_match:
                vod_actor = act_match.group(1).strip()
            desc_match = re.search(r'剧情简介\s*(.+)', text, re.DOTALL)
            if desc_match:
                vod_content = desc_match.group(1).strip()
            elif re.search(r'简介\s*(.+)', text, re.DOTALL):
                vod_content = re.search(r'简介\s*(.+)', text, re.DOTALL).group(1).strip()

        # ---------- 分集解析（多线路）----------
        play_from_list = []
        play_url_list = []

        # 尝试从 episodeManager 解析
        ep_manager = soup.select_one('[x-data*="episodeManager"]')
        if ep_manager:
            xdata = ep_manager.get('x-data', '')
            # 提取线路名称列表：episodeManager(1, 1, [{ lineName: 'alists', episodeCount: 1 }])
            lines_name = []
            match_lines = re.search(r'\[\s*\{[^}]*lineName\s*:\s*\'([^\']+)\'[^}]*\}\s*\]', xdata)
            if match_lines:
                lines_name = [match_lines.group(1)]
            else:
                # 尝试匹配多个
                lines_name = re.findall(r'lineName\s*:\s*\'([^\']+)\'', xdata)
            if not lines_name:
                lines_name = ['线路1']

            # 收集所有剧集链接
            episode_links = ep_manager.select('a[data-episode]')
            lines_eps = {}
            for a in episode_links:
                line = a.get('data-line', '1')
                ep = a.get('data-episode', '')
                href = a.get('href', '')
                if not href or not ep:
                    continue
                full_url = href if href.startswith('http') else self.site_url + href
                lines_eps.setdefault(line, []).append((int(ep), full_url))

            # 按线路生成播放串
            for idx, line_key in enumerate(sorted(lines_eps.keys())):
                eps = sorted(lines_eps[line_key], key=lambda x: x[0])
                line_name = lines_name[idx] if idx < len(lines_name) else f'线路{line_key}'
                if not eps:
                    continue
                episode_strs = [f"第{ep[0]}集${ep[1]}" for ep in eps]
                play_from_list.append(line_name)
                play_url_list.append('#'.join(episode_strs))

        # 如果没有分集（单集电影），则直接使用当前页
        if not play_url_list:
            play_from_list.append('播放')
            play_url_list.append(f"正片${self.site_url}/play/{vod_id}")

        vod_play_from = '$$$'.join(play_from_list)
        vod_play_url = '$$$'.join(play_url_list)

        result = [{
            "vod_id": vod_id,
            "vod_name": vod_name,
            "vod_pic": vod_pic,
            "vod_content": vod_content,
            "vod_actor": vod_actor,
            "vod_director": vod_director,
            "vod_area": "",
            "vod_year": "",
            "vod_play_from": vod_play_from,
            "vod_play_url": vod_play_url
        }]
        return {"list": result}

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg="1"):
        page = int(pg) if pg else 1
        params = {"q": key}
        if page > 1:
            params['page'] = page
        soup = self._fetch_html('/search', params=params)
        if not soup:
            return {"list": [], "page": page, "pagecount": 1}

        cards = soup.select('div[data-vod-id]')
        video_list = []
        if cards:
            for card in cards[:30]:
                v = self._extract_video_card(card)
                if v:
                    video_list.append(v)
        else:
            # 降级解析
            for a in soup.select('a.block[href^="/play/"]'):
                href = a.get('href', '')
                vod_id = href.replace('/play/', '').strip()
                if not vod_id:
                    continue
                h3 = a.select_one('h3')
                vod_name = h3.get_text(strip=True) if h3 else href
                if not vod_name:
                    continue
                img = a.select_one('img[data-src]')
                vod_pic = ''
                if img:
                    src = img.get('data-src', '')
                    if src and not src.startswith('data:'):
                        vod_pic = src if src.startswith('http') else 'https:' + src
                video_list.append({
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                    "vod_pic": vod_pic,
                    "vod_remarks": ''
                })
        return {"list": video_list, "page": page, "pagecount": 1}

    # ---------- 播放器：从播放页面提取真实视频地址 ----------
    def playerContent(self, flag, id, vipFlags):
        # id 可能是 /play/xxxx 或完整URL，也可能是直接带$符号的完整链接（由vod_play_url传入）
        if '$' in id:
            # 格式为 "第x集$url"，提取url部分
            parts = id.split('$', 1)
            if len(parts) == 2:
                id = parts[1]

        if not id.startswith('http'):
            url = f"{self.site_url}{id}" if id.startswith('/') else f"{self.site_url}/play/{id}"
        else:
            url = id

        # 请求播放页面
        resp = self.fetch(url, headers=self.headers)
        if not resp:
            return {"parse": 1, "url": url, "header": self.headers}

        html = resp.text

        # 方法1: 查找 var player_aaaa = {...}
        match = re.search(r'var\s+player_aaaa\s*=\s*(\{.*?\});', html, re.S)
        if match:
            try:
                data = json.loads(match.group(1))
                video_url = data.get('url', '')
                if video_url and (video_url.endswith('.m3u8') or video_url.endswith('.mp4')):
                    return {"parse": 0, "url": video_url, "header": self.headers}
            except:
                pass

        # 方法2: 查找 "url":"http...m3u8"
        match = re.search(r'"url"\s*:\s*"([^"]+\.m3u8[^"]*)"', html)
        if match:
            video_url = match.group(1).replace('\\/', '/')
            return {"parse": 0, "url": video_url, "header": self.headers}

        # 方法3: 查找 video 标签的 src
        match = re.search(r'<video[^>]+src="([^"]+\.m3u8[^"]*)"', html)
        if match:
            video_url = match.group(1)
            return {"parse": 0, "url": video_url, "header": self.headers}

        # 方法4: 查找 source 标签
        match = re.search(r'<source\s+src="([^"]+\.m3u8[^"]*)"', html)
        if match:
            video_url = match.group(1)
            return {"parse": 0, "url": video_url, "header": self.headers}

        # 方法5: 查找 window._pdf 或其它加密变量（简单解码）
        # 示例: window._pdf = "WyJvc3MuZG91eWluYml0LmNvbSIsIm15b3NzLmRvdXlpbmJpdC50b3AiXQ=="
        match_pdf = re.search(r'window\._pdf\s*=\s*"([^"]+)"', html)
        if match_pdf:
            try:
                import base64
                decoded = base64.b64decode(match_pdf.group(1)).decode('utf-8')
                # 可能得到域名列表，但还需结合vid构造url，暂不处理
            except:
                pass

        # 无法解析真实地址，返回页面URL让外部解析器处理
        return {"parse": 1, "url": url, "header": self.headers}

    # 可选：本地代理（本例不需要）
    def localProxy(self, param=''):
        return {}
