# -*- coding: utf-8 -*-
"""
目标站: 4kvm (道长DR框架格式)
"""
import re
import json
import time
import random
import urllib.parse
from bs4 import BeautifulSoup
from base.spider import Spider


class Spider(Spider):
    # 道长格式：类属性
    def_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }
    host = 'https://www.4kvm.net'

    def getName(self):
        return '4KVM'

    def init(self, extend=''):
        # 建立会话（可选）
        try:
            self._fetch('/')
        except:
            pass

    # ---------- 首页 ----------
    def homeContent(self, filter):
        html = self._fetch('/')
        return {
            'class': [
                {'type_id': '1', 'type_name': '电影'},
                {'type_id': '2', 'type_name': '电视剧'},
                {'type_id': '3', 'type_name': '动漫'},
            ],
            'list': self._extractList(html) if html else []
        }

    def homeVideoContent(self):
        return self.categoryContent('1', 1, {}, {})

    # ---------- 分类 ----------
    def categoryContent(self, tid, pg, filter, extend):
        page = int(pg) if pg else 1
        params = {'classify': tid}
        if extend:
            for k, v in extend.items():
                if v and k != 'classify':
                    params[k] = v
        if page > 1:
            params['page'] = page

        query = urllib.parse.urlencode(params)
        html = self._fetch(f'/filter?{query}')
        return {
            'page': page,
            'pagecount': 99,          # 模板值，可按实际解析调整
            'limit': 24,
            'total': 999,
            'list': self._extractList(html) if html else []
        }

    # ---------- 详情 ----------
    def detailContent(self, ids):
        result = {'list': []}
        vid = ids[0].split(',')[0].strip()
        try:
            html = self._fetch(f'/play/{vid}')
            if not html:
                return result

            soup = BeautifulSoup(html, 'html.parser')

            # 标题
            title_tag = soup.select_one('h1') or soup.select_one('h2')
            vod_name = title_tag.get_text(strip=True) if title_tag else vid

            # 海报
            vod_pic = ''
            img = soup.select_one('img.w-full') or soup.select_one('img[data-src]') or soup.select_one('img[src]')
            if img:
                src = img.get('data-src') or img.get('src') or ''
                if src and not src.startswith('data:'):
                    vod_pic = self._fixPic(src)

            # 导演/演员/简介
            vod_director = ''
            vod_actor = ''
            vod_content = ''
            info = soup.select_one('.rounded-lg') or soup.select_one('div.grid')
            if info:
                txt = info.get_text(' ', strip=True)
                dm = re.search(r'导演[：:]\s*([^主演\n]+)', txt)
                if dm: vod_director = dm.group(1).strip()
                am = re.search(r'主演[：:]\s*([^剧\n]+)', txt)
                if am: vod_actor = am.group(1).strip()
                cm = re.search(r'(?:剧情)?简介[：:]\s*(.+?)(?:\n|$)', txt)
                if cm: vod_content = cm.group(1).strip()

            # 分集解析 (episodeManager)
            play_from, play_url = [], []
            ep_mgr = soup.select_one('[x-data*="episodeManager"]')
            if ep_mgr:
                lines = {}
                for a in ep_mgr.select('a[data-episode][href]'):
                    line = a.get('data-line', '1')
                    ep = a.get('data-episode', '')
                    href = a.get('href', '')
                    if not href:
                        continue
                    if href.startswith('/'):
                        href = self.host + href
                    lines.setdefault(line, []).append((int(ep) if ep else 0, href, a.get_text(strip=True)))
                for line_key in sorted(lines.keys()):
                    eps = sorted(lines[line_key], key=lambda x: x[0])
                    ep_strs = [f'{e[2] or "第"+str(e[0])+"集"}${e[1]}' for e in eps]
                    if ep_strs:
                        play_from.append(f'线路{line_key}')
                        play_url.append('#'.join(ep_strs))
            # 回退
            if not play_url:
                play_from.append('播放')
                play_url.append(f'播放${vid}')

            result['list'].append({
                'vod_id': vid,
                'vod_name': vod_name,
                'vod_pic': vod_pic,
                'vod_director': vod_director,
                'vod_actor': vod_actor,
                'vod_content': vod_content,
                'vod_play_from': '$$$'.join(play_from),
                'vod_play_url': '$$$'.join(play_url)
            })
        except:
            pass
        return result

    # ---------- 搜索 ----------
    def searchContent(self, key, quick, pg='1'):
        page = int(pg) if pg else 1
        params = {'q': key}
        if page > 1:
            params['page'] = page
        query = urllib.parse.urlencode(params)
        html = self._fetch(f'/search?{query}')
        return {
            'list': self._extractList(html) if html else [],
            'page': page,
            'pagecount': 1,
            'limit': 24,
            'total': 0
        }

    # ---------- 播放器 ----------
    def playerContent(self, flag, id, vipFlags):
        try:
            url = f'{self.host}/play/{id}' if not id.startswith('http') else id
            html = self._fetch(f'/play/{id}')
            if not html:
                return {'parse': 1, 'url': url, 'header': self.def_headers}

            header = {
                'User-Agent': self.def_headers['User-Agent'],
                'Referer': self.host + '/'
            }

            # 1. player_aaaa
            m = re.search(r'player_aaaa\s*=\s*(\{[^;]+\})', html, re.S)
            if m:
                try:
                    pd = json.loads(m.group(1))
                    pu = pd.get('url') or pd.get('src') or ''
                    if pu:
                        if pu.startswith('//'):
                            pu = 'https:' + pu
                        if pu.endswith('.m3u8') or pu.endswith('.mp4'):
                            return {'parse': 0, 'url': pu, 'header': header}
                        if pu.startswith('http'):
                            return {'parse': 1, 'url': pu, 'header': header}
                except:
                    pass

            # 2. 正则提取 m3u8/mp4
            patterns = [
                r'url\s*:\s*[\'"]([^\'"]+\.m3u8)[\'"]',
                r'url\s*:\s*[\'"]([^\'"]+\.mp4)[\'"]',
                r'src\s*:\s*[\'"]([^\'"]+\.m3u8)[\'"]',
                r'[\'"]([^\'"]*\.m3u8[^\'"]*)[\'"]',
            ]
            for pat in patterns:
                m = re.search(pat, html, re.I)
                if m:
                    pu = m.group(1)
                    if pu.startswith('//'):
                        pu = 'https:' + pu
                    return {'parse': 0, 'url': pu, 'header': header}

            # 3. iframe
            soup = BeautifulSoup(html, 'html.parser')
            iframe = soup.find('iframe')
            if iframe and iframe.get('src'):
                src = iframe['src']
                if src.startswith('//'):
                    src = 'https:' + src
                elif not src.startswith('http'):
                    src = self.host + '/' + src.lstrip('/')
                return {'parse': 1, 'url': src, 'header': header}

            return {'parse': 1, 'url': url, 'header': self.def_headers}
        except:
            return {'parse': 1, 'url': id, 'header': self.def_headers}

    # ---------- 工具 ----------
    def _fetch(self, url):
        try:
            if not url.startswith('http'):
                url = self.host + url
            time.sleep(random.uniform(0.3, 0.7))
            rsp = self.fetch(url, headers=self.def_headers, verify=False)
            return rsp.text if rsp and rsp.status_code == 200 else ''
        except:
            return ''

    def _fixPic(self, u):
        if not u:
            return ''
        if u.startswith('//'):
            return 'https:' + u
        if not u.startswith('http'):
            return self.host + '/' + u.lstrip('/')
        return u.replace('&amp;', '&')

    def _extractList(self, html):
        """使用BeautifulSoup稳定解析视频列表（兼容道长格式）"""
        videos = []
        seen = set()
        try:
            soup = BeautifulSoup(html, 'html.parser')
            cards = soup.select('div[data-vod-id]')
            if not cards:
                cards = soup.find_all('a', href=re.compile(r'/play/'))
            for card in cards:
                try:
                    # 获取链接
                    if card.name == 'a' and '/play/' in card.get('href', ''):
                        a = card
                    else:
                        a = card.find('a', href=re.compile(r'/play/'))
                    if not a:
                        continue

                    href = a.get('href', '')
                    vid = href.split('/play/')[-1].strip()
                    if not vid or vid in seen:
                        continue
                    seen.add(vid)

                    # 标题
                    if card.name == 'a':
                        title = card.get('title') or card.get_text(strip=True)
                    else:
                        h = card.find('h3') or card.find('h2')
                        title = h.get_text(strip=True) if h else a.get_text(strip=True)
                    if not title:
                        title = vid

                    # 图片
                    pic = ''
                    img = card.find('img') if card.name != 'img' else card
                    if img:
                        src = img.get('data-src') or img.get('src') or ''
                        if src and not src.startswith('data:'):
                            pic = self._fixPic(src)

                    # 备注
                    remark = ''
                    for cls in ('.pic-text', '.remarks', '.text-green-500', '.text-yellow-400'):
                        tag = card.select_one(cls)
                        if tag:
                            remark = tag.get_text(strip=True)
                            break

                    videos.append({
                        'vod_id': vid,
                        'vod_name': title.strip(),
                        'vod_pic': pic,
                        'vod_remarks': remark
                    })
                except:
                    continue
        except:
            pass
        return videos

    def localProxy(self, param=''):
        return {}

    def isVideoFormat(self, url):
        return url.endswith(('.m3u8', '.mp4')) if url else False

    def manualVideoCheck(self):
        return False
