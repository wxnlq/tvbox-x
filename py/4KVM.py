# coding=utf-8
"""
目标站: 4kvm  首页: https://www.4kvm.net
动态筛选、精准分集、去重列表
功能：完整实现爬虫逻辑，支持分类、筛选、搜索、详情、播放源解析
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
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        self.categories = [
            {"type_id": "1", "type_name": "电影"},
            {"type_id": "2", "type_name": "电视剧"},
            {"type_id": "3", "type_name": "动漫"}
        ]
        self._filters_cache = None  # 筛选条件缓存
        self._seen_vod_ids = set()  # 去重集合

    # ================= 工具方法 =================
    def _clear_seen(self):
        """清空去重集合"""
        self._seen_vod_ids.clear()

    def _fix_url(self, url):
        """补全URL"""
        if not url:
            return ""
        if url.startswith('//'):
            return f"https:{url}"
        if url.startswith('/'):
            return f"{self.site_url}{url}"
        if not url.startswith('http'):
            return f"{self.site_url}/{url.lstrip('/')}"
        return url

    def _safe_extract(self, elem, selector, attr=None, default=""):
        """安全提取元素内容"""
        target = elem.select_one(selector) if elem else None
        if not target:
            return default
        if attr:
            return target.get(attr, default).strip()
        return target.get_text(strip=True) or default

    # ================= 动态筛选解析 =================
    def _fetch_filters_for_classify(self, tid):
        """请求 /filter?classify=tid，解析页面筛选区域，返回该分类的筛选列表"""
        try:
            url = f"{self.site_url}/filter?classify={tid}"
            resp = self.fetch(url, headers=self.headers, timeout=10)
            if not resp:
                return []
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            filter_groups = []
            # 匹配筛选容器（兼容不同布局）
            containers = soup.select('main div.flex.flex-wrap.items-center.gap-3, div.filter-group')
            
            for container in containers:
                links = container.select('a[href]')
                if len(links) < 2:
                    continue
                
                first_text = self._safe_extract(container, 'a:first-child')
                if not first_text.startswith('全部'):
                    continue
                
                group_name = first_text.replace('全部', '').strip() or f"筛选{len(filter_groups)+1}"
                param_key = None
                
                # 提取筛选参数名
                for a in links[1:]:
                    href = self._safe_extract(a, '', 'href')
                    parsed = urllib.parse.urlparse(href)
                    qs = urllib.parse.parse_qs(parsed.query)
                    for k in qs:
                        if k not in ('classify', 'page', 'sort_by', 'order'):
                            param_key = k
                            break
                    if param_key:
                        break
                
                if not param_key:
                    continue
                
                # 构建筛选选项
                options = []
                for a in links:
                    text = self._safe_extract(a, '')
                    href = self._safe_extract(a, '', 'href')
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
        except Exception as e:
            print(f"解析筛选条件失败: {e}")
            return []

    def _get_all_filters(self):
        """获取所有分类的筛选条件（带缓存）"""
        if self._filters_cache is not None:
            return self._filters_cache
        
        filters = {}
        for cat in self.categories:
            tid = cat["type_id"]
            groups = self._fetch_filters_for_classify(tid)
            if groups:
                filters[tid] = groups
        
        # 为无筛选的分类复用电影分类的筛选
        if "1" in filters:
            for tid in ["2", "3"]:
                if tid not in filters:
                    filters[tid] = filters["1"]
        
        self._filters_cache = filters
        return filters

    # ================= 核心业务方法 =================
    def homeContent(self, filter):
        """首页内容（分类+推荐列表+筛选条件）"""
        self._clear_seen()
        video_list = []
        try:
            resp = self.fetch(self.site_url, headers=self.headers, timeout=10)
            if resp:
                soup = BeautifulSoup(resp.text, 'html.parser')
                # 解析视频卡片（兼容多布局）
                cards = soup.select('div[data-vod-id], div[class*="vod-card"], a[href^="/play/"]:has(img)')
                
                for card in cards[:20]:  # 首页只取前20条
                    # 提取vod_id
                    vod_id = card.get('data-vod-id', '').strip()
                    if not vod_id:
                        href = self._safe_extract(card, 'a.block[href^="/play/"]', 'href') or self._safe_extract(card, '', 'href')
                        vod_id = re.sub(r'^/play/', '', href).strip()
                    if not vod_id or vod_id in self._seen_vod_ids:
                        continue
                    
                    # 提取基础信息
                    vod_name = self._safe_extract(card, 'h3.text-white, h3, .vod-title')
                    vod_pic = self._safe_extract(card, 'img[data-src], img[src]', 'data-src') or self._safe_extract(card, 'img[data-src], img[src]', 'src')
                    vod_remarks = self._safe_extract(card, '.text-green-500, .text-yellow-400, span[class*="px-1.5"], .vod-tag')
                    
                    # 数据校验
                    if not vod_name:
                        continue
                    
                    # 补全图片URL
                    vod_pic = self._fix_url(vod_pic)
                    if 'nopic' in vod_pic.lower() or not vod_pic:
                        vod_pic = ""
                    
                    # 去重并添加
                    self._seen_vod_ids.add(vod_id)
                    video_list.append({
                        "vod_id": vod_id,
                        "vod_name": vod_name,
                        "vod_pic": vod_pic,
                        "vod_remarks": vod_remarks
                    })
        except Exception as e:
            print(f"解析首页内容失败: {e}")
        
        return {
            "class": self.categories,
            "list": video_list,
            "filters": self._get_all_filters()
        }

    def homeVideoContent(self):
        """首页视频列表（复用homeContent）"""
        return self.homeContent(False)

    def categoryContent(self, tid, pg, filter, extend):
        """分类内容（带分页+筛选）"""
        self._clear_seen()
        page = int(pg) if pg and pg.isdigit() else 1
        video_list = []
        pagecount = 1
        total = 0
        
        try:
            # 构建请求参数
            params = {"classify": tid}
            if extend and isinstance(extend, dict):
                for k, v in extend.items():
                    if v and k not in ('classify', 'page'):
                        params[k] = v
            if page > 1:
                params['page'] = page
            
            # 构建请求URL
            query = urllib.parse.urlencode(params)
            url = f"{self.site_url}/filter?{query}"
            resp = self.fetch(url, headers=self.headers, timeout=10)
            
            if not resp:
                return {"list": [], "page": page, "pagecount": 1, "limit": 24, "total": 0}
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 解析视频列表
            cards = soup.select('div[data-vod-id], div[class*="vod-card"], a[href^="/play/"]:has(img)')
            for card in cards:
                # 提取vod_id
                vod_id = card.get('data-vod-id', '').strip()
                if not vod_id:
                    href = self._safe_extract(card, 'a.block[href^="/play/"]', 'href') or self._safe_extract(card, '', 'href')
                    vod_id = re.sub(r'^/play/', '', href).strip()
                if not vod_id or vod_id in self._seen_vod_ids:
                    continue
                
                # 提取基础信息
                vod_name = self._safe_extract(card, 'h3.text-white, h3, .vod-title')
                vod_pic = self._safe_extract(card, 'img[data-src], img[src]', 'data-src') or self._safe_extract(card, 'img[data-src], img[src]', 'src')
                vod_remarks = self._safe_extract(card, '.text-green-500, .text-yellow-400, span[class*="px-1.5"], .vod-tag')
                
                # 数据校验
                if not vod_name:
                    continue
                
                # 补全图片URL
                vod_pic = self._fix_url(vod_pic)
                if 'nopic' in vod_pic.lower() or not vod_pic:
                    vod_pic = ""
                
                # 去重并添加
                self._seen_vod_ids.add(vod_id)
                video_list.append({
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                    "vod_pic": vod_pic,
                    "vod_remarks": vod_remarks
                })
            
            # 解析分页信息
            # 方式1：匹配"共X页"文本
            page_text = soup.find(string=re.compile(r'共\s*\d+\s*页'))
            if page_text:
                nums = re.findall(r'\d+', page_text)
                if nums:
                    pagecount = int(nums[-1])
            # 方式2：解析分页链接
            else:
                page_links = soup.select('a[href*="page="]')
                for a in page_links:
                    text = self._safe_extract(a, '')
                    if text.isdigit():
                        pagecount = max(pagecount, int(text))
            
            # 计算总数
            total = len(video_list) * pagecount if pagecount > 0 else 0
            
        except Exception as e:
            print(f"解析分类内容失败: {e}")
        
        return {
            "list": video_list,
            "page": page,
            "pagecount": pagecount,
            "limit": 24,
            "total": total
        }

    def detailContent(self, ids):
        """详情页内容（含分集播放地址）"""
        if not ids or not ids[0]:
            return {"list": []}
        
        vod_id = ids[0].strip()
        result = []
        play_from_list = []
        play_url_list = []
        
        try:
            # 请求详情页
            url = f"{self.site_url}/play/{vod_id}"
            resp = self.fetch(url, headers=self.headers, timeout=10)
            if not resp or resp.status_code != 200:
                return {"list": []}
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 1. 基础信息解析
            vod_name = self._safe_extract(soup, 'h1.text-xl, h1, h2, .vod-name') or vod_id
            vod_pic = self._safe_extract(soup, 'img.w-full, img[src], img[data-src]', 'data-src') or self._safe_extract(soup, 'img.w-full, img[src], img[data-src]', 'src')
            vod_pic = self._fix_url(vod_pic)
            if 'nopic' in vod_pic.lower() or not vod_pic:
                vod_pic = ""
            
            # 2. 导演/主演/简介解析
            vod_director = ""
            vod_actor = ""
            vod_content = ""
            info_block = soup.select_one('.rounded-lg div.grid, div.grid, .vod-info, .info-block')
            
            if info_block:
                info_text = info_block.get_text(' ', strip=True)
                # 解析导演
                dir_match = re.search(r'导演\s*[:：]?\s*([^主演主演剧]+)', info_text)
                if dir_match:
                    vod_director = dir_match.group(1).strip()
                # 解析主演
                act_match = re.search(r'主演\s*[:：]?\s*([^剧情简介]+)', info_text)
                if act_match:
                    vod_actor = act_match.group(1).strip()
                # 解析简介
                desc_match = re.search(r'剧情简介\s*[:：]?\s*(.+)', info_text, re.DOTALL)
                if not desc_match:
                    desc_match = re.search(r'简介\s*[:：]?\s*(.+)', info_text, re.DOTALL)
                if desc_match:
                    vod_content = desc_match.group(1).strip()
            
            # 3. 播放源/分集解析（核心）
            # 方式1：解析episodeManager（动态渲染的分集）
            episode_manager = soup.select_one('[x-data*="episodeManager"], .episode-list, .play-list')
            if episode_manager:
                # 提取线路信息
                line_names = []
                line_matches = re.findall(r'lineName\s*:\s*[\'"]([^\'"]+)', episode_manager.get('x-data', ''))
                if line_matches:
                    line_names = line_matches
                else:
                    # 回退：从DOM提取线路名
                    line_elems = episode_manager.select('.line-name, .play-source-name')
                    line_names = [self._safe_extract(elem, '') for elem in line_elems if self._safe_extract(elem, '')]
                
                # 提取分集链接
                episode_links = episode_manager.select('a[data-episode], a[href*="/play/"], a[class*="episode"]')
                line_eps = {}  # 按线路分组存储分集 {线路名: [(集数, 播放地址), ...]}
                
                for a in episode_links:
                    # 提取线路标识
                    line_key = a.get('data-line', '1')
                    line_name = line_names[int(line_key)-1] if (line_names and int(line_key)-1 < len(line_names)) else f'线路{line_key}'
                    # 提取集数和播放地址
                    ep_num = self._safe_extract(a, '', 'data-episode') or self._safe_extract(a, '')
                    ep_href = self._safe_extract(a, '', 'href')
                    
                    if not ep_href or not ep_num:
                        continue
                    
                    # 补全播放地址
                    full_url = self._fix_url(ep_href)
                    # 格式化分集字符串（格式："第1集$播放地址"）
                    line_eps.setdefault(line_name, []).append((ep_num, full_url))
                
                # 整理播放源
                for line_name, eps in line_eps.items():
                    # 集数排序
                    eps_sorted = sorted(eps, key=lambda x: int(re.findall(r'\d+', x[0])[0]) if re.findall(r'\d+', x[0]) else 0)
                    # 拼接成分集字符串
                    ep_strs = [f"{ep[0]}${ep[1]}" for ep in eps_sorted]
                    if ep_strs:
                        play_from_list.append(line_name)
                        play_url_list.append('#'.join(ep_strs))
            
            # 方式2：解析播放器容器中的真实播放地址（直接播放的场景）
            if not play_url_list:
                # 查找播放器配置
                player_script = soup.find('script', string=re.compile(r'player|video|src|url'))
                if player_script:
                    # 提取m3u8/mp4等真实播放地址
                    url_matches = re.findall(r'https?://[^\s"\']+\.(m3u8|mp4|flv|mov)', player_script.text)
                    if url_matches:
                        play_from_list.append('默认线路')
                        play_url_list.append(f"播放${url_matches[0]}")
                # 回退：使用当前页作为播放地址
                else:
                    play_from_list.append('默认线路')
                    play_url_list.append(f"播放${self._fix_url(f'/play/{vod_id}')}")
            
            # 4. 组装结果
            vod_play_from = '$$$'.join(play_from_list)
            vod_play_url = '$$$'.join(play_url_list)
            
            result.append({
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_director": vod_director,
                "vod_actor": vod_actor,
                "vod_content": vod_content,
                "vod_area": "",
                "vod_year": "",
                "vod_play_from": vod_play_from,
                "vod_play_url": vod_play_url
            })
            
        except Exception as e:
            print(f"解析详情页失败: {e}")
        
        return {"list": result}

    def searchContent(self, key, quick, pg="1"):
        """搜索功能"""
        self._clear_seen()
        page = int(pg) if pg and pg.isdigit() else 1
        video_list = []
        
        try:
            # 构建搜索URL
            params = {"q": key}
            if page > 1:
                params['page'] = page
            query = urllib.parse.urlencode(params)
            url = f"{self.site_url}/search?{query}"
            
            resp = self.fetch(url, headers=self.headers, timeout=10)
            if not resp:
                return {"list": [], "page": page, "pagecount": 1}
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            
            # 解析搜索结果
            cards = soup.select('div[data-vod-id], div[class*="vod-card"], a[href^="/play/"]:has(img)')
            if not cards:
                # 降级处理：直接查找所有播放链接
                cards = soup.select('a[href^="/play/"]')
            
            for card in cards[:30]:  # 搜索结果最多取30条
                # 提取vod_id
                vod_id = card.get('data-vod-id', '').strip()
                if not vod_id:
                    href = self._safe_extract(card, '', 'href')
                    vod_id = re.sub(r'^/play/', '', href).strip()
                if not vod_id or vod_id in self._seen_vod_ids:
                    continue
                
                # 提取基础信息
                vod_name = self._safe_extract(card, 'h3.text-white, h3, .vod-title, .search-title')
                vod_pic = self._safe_extract(card, 'img[data-src], img[src]', 'data-src') or self._safe_extract(card, 'img[data-src], img[src]', 'src')
                vod_remarks = self._safe_extract(card, '.text-green-500, .text-yellow-400, span[class*="px-1.5"], .vod-tag')
                
                # 数据校验
                if not vod_name:
                    continue
                
                # 补全图片URL
                vod_pic = self._fix_url(vod_pic)
                if 'nopic' in vod_pic.lower() or not vod_pic:
                    vod_pic = ""
                
                # 去重并添加
                self._seen_vod_ids.add(vod_id)
                video_list.append({
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                    "vod_pic": vod_pic,
                    "vod_remarks": vod_remarks
                })
                
        except Exception as e:
            print(f"解析搜索结果失败: {e}")
        
        return {
            "list": video_list,
            "page": page,
            "pagecount": 1  # 搜索页默认1页，可根据实际分页调整
        }

    def playerContent(self, flag, id, vipFlags):
        """解析播放地址（核心：获取真实播放源）"""
        try:
            # 1. 处理ID，补全URL
            if not id.startswith('http'):
                play_url = f"{self.site_url}/play/{id}"
            else:
                play_url = id
            
            # 2. 请求播放页，提取真实播放地址
            resp = self.fetch(play_url, headers=self.headers, timeout=15)
            if not resp:
                return {"parse": 1, "url": play_url, "header": self.headers}
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            html_text = resp.text
            
            # 3. 提取真实播放地址（优先级：m3u8 > mp4 > flv > 原页）
            # 方式1：从JS变量中提取
            url_matches = re.findall(r'var\s+[^\s=]+\s*=\s*[\'"](https?://[^\s"\']+\.(m3u8|mp4|flv))[\'"]', html_text)
            if url_matches:
                real_url = url_matches[0][0]
                header = {
                    'User-Agent': self.headers['User-Agent'],
                    'Referer': self.site_url + '/'
                }
                # 直接返回可播放的地址（无需二次解析）
                if real_url.endswith(('.m3u8', '.mp4', '.flv')):
                    return {"parse": 0, "url": real_url, "header": header}
                else:
                    return {"parse": 1, "url": real_url, "header": header}
            
            # 方式2：从iframe中提取
            iframe = soup.select_one('iframe[src]')
            if iframe:
                iframe_src = self._fix_url(self._safe_extract(iframe, '', 'src'))
                return {"parse": 1, "url": iframe_src, "header": self.headers}
            
            # 方式3：从播放器容器提取
            player_div = soup.select_one('#player, .player-container, [id*="player"]')
            if player_div:
                # 查找内嵌的播放地址
                data_src = self._safe_extract(player_div, '', 'data-src') or self._safe_extract(player_div, '', 'data-url')
                if data_src:
                    real_url = self._fix_url(data_src)
                    return {"parse": 0 if real_url.endswith(('.m3u8', '.mp4')) else 1, "url": real_url, "header": self.headers}
            
            # 回退：返回原地址，由上层解析
            return {"parse": 1, "url": play_url, "header": self.headers}
            
        except Exception as e:
            print(f"解析播放地址失败: {e}")
            return {"parse": 1, "url": id if id.startswith('http') else f"{self.site_url}/play/{id}", "header": self.headers}

    # 以下为可选实现（根据base.spider要求）
    def localProxy(self, param=''):
        return {}

    def isVideoFormat(self, url):
        """判断是否为直接播放的视频格式"""
        return url.endswith(('.m3u8', '.mp4', '.flv', '.mov', '.avi'))

    def manualVideoCheck(self):
        return False
