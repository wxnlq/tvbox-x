# -*- coding: utf-8 -*-
"""
目标站: 4kvm
首页: https://www.4kvm.net
功能: 动态筛选、精准分集、解析播放源地址
"""
import re
import sys
import json
import time
import random
import urllib.parse
from bs4 import BeautifulSoup

sys.path.append('..')
from base.spider import Spider


class Spider(Spider):
    # 请求头配置
    def_headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Referer': 'https://www.4kvm.net/',
        'Connection': 'keep-alive',
    }

    # 站点配置
    host = 'https://www.4kvm.net'
    
    # 分类配置
    categories = [
        {"type_id": "1", "type_name": "电影"},
        {"type_id": "2", "type_name": "电视剧"},
        {"type_id": "3", "type_name": "动漫"},
        {"type_id": "4", "type_name": "综艺"},
    ]
    
    # 筛选参数映射
    filter_keys = {
        "1": ["class", "area", "lang", "year", "sort_by", "order"],
        "2": ["class", "area", "lang", "year", "sort_by", "order"],
        "3": ["class", "area", "lang", "year", "sort_by", "order"],
        "4": ["class", "area", "year", "sort_by", "order"],
    }

    def getName(self):
        return "4kvm"

    def init(self, extend=''):
        """初始化，获取首页建立会话"""
        try:
            self.fetch(self.host, headers=self.def_headers)
        except Exception as e:
            print(f"初始化失败: {e}")

    # ==================== 首页内容 ====================
    def homeContent(self, filter):
        """首页内容"""
        url = self.host + "/"
        html = self._fetch(url)
        if not html:
            return {"class": self.categories, "list": [], "filters": {}}
        
        soup = BeautifulSoup(html, 'html.parser')
        video_list = self._parse_video_cards(soup, limit=24)
        
        # 动态获取筛选条件
        filters = self._get_dynamic_filters()
        
        return {
            "class": self.categories,
            "list": video_list,
            "filters": filters
        }

    def homeVideoContent(self):
        """首页视频内容"""
        return self.homeContent(False)

    # ==================== 分类内容 ====================
    def categoryContent(self, tid, pg, filter, extend):
        """分类内容"""
        page = int(pg) if pg else 1
        
        # 构建请求参数
        params = {"classify": tid}
        if extend:
            for k, v in extend.items():
                if v and v != '':
                    params[k] = v
        if page > 1:
            params['page'] = page
        
        query = urllib.parse.urlencode(params)
        url = f"{self.host}/filter?{query}"
        
        html = self._fetch(url)
        if not html:
            return {"list": [], "page": page, "pagecount": 1, "limit": 24, "total": 0}
        
        soup = BeautifulSoup(html, 'html.parser')
        video_list = self._parse_video_cards(soup)
        
        # 解析分页
        pagecount = self._parse_pagecount(soup, page)
        
        return {
            "list": video_list,
            "page": page,
            "pagecount": pagecount,
            "limit": 24,
            "total": len(video_list) * pagecount
        }

    # ==================== 搜索内容 ====================
    def searchContent(self, key, quick, pg='1'):
        """搜索内容"""
        page = int(pg) if pg else 1
        params = {"q": key}
        if page > 1:
            params['page'] = page
        
        query = urllib.parse.urlencode(params)
        url = f"{self.host}/search?{query}"
        
        html = self._fetch(url)
        if not html:
            return {"list": [], "page": page, "pagecount": 1, "limit": 24, "total": 0}
        
        soup = BeautifulSoup(html, 'html.parser')
        video_list = self._parse_video_cards(soup)
        
        return {
            "list": video_list,
            "page": page,
            "pagecount": 1,
            "limit": 24,
            "total": len(video_list)
        }

    # ==================== 详情内容 ====================
    def detailContent(self, ids):
        """详情内容 - 核心解析区域"""
        if not ids:
            return {"list": []}
        
        vod_id = ids[0]
        url = f"{self.host}/play/{vod_id}"
        
        html = self._fetch(url)
        if not html:
            return {"list": []}
        
        soup = BeautifulSoup(html, 'html.parser')
        
        # 解析基本信息
        vod_name = self._parse_title(soup, vod_id)
        vod_pic = self._parse_poster(soup)
        vod_director, vod_actor, vod_content = self._parse_info(soup)
        
        # 解析分集和播放地址
        play_from_list, play_url_list = self._parse_episodes(soup, vod_id)
        
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

    # ==================== 播放器内容 ====================
    def playerContent(self, flag, id, vipFlags):
        """
        播放器内容解析
        核心功能：根据分集ID获取真实的视频播放地址
        """
        try:
            # 如果id是完整的URL，直接使用
            if id.startswith('http'):
                url = id
            else:
                url = f"{self.host}/play/{id}"
            
            # 添加随机延迟，避免请求过快
            time.sleep(random.uniform(0.5, 1.5))
            
            html = self._fetch(url)
            if not html:
                return self._fallback_player(id)
            
            # 获取当前页面的cookie和headers
            headers = {
                'User-Agent': self.def_headers['User-Agent'],
                'Referer': url,
                'Accept': '*/*',
                'Accept-Language': 'zh-CN,zh;q=0.9',
            }
            
            # 方法1: 从episodeManager中解析播放地址
            player_data = self._extract_player_data(html)
            if player_data:
                video_url = player_data.get('url', '')
                if video_url:
                    # 处理不同类型的播放地址
                    if video_url.endswith('.m3u8'):
                        return {
                            "parse": 0,
                            "url": video_url,
                            "header": headers
                        }
                    elif video_url.endswith('.mp4'):
                        return {
                            "parse": 0,
                            "url": video_url,
                            "header": headers
                        }
                    elif video_url.startswith('http'):
                        return {
                            "parse": 1,
                            "url": video_url,
                            "header": headers
                        }
            
            # 方法2: 从script标签中提取
            video_url = self._extract_video_from_script(html)
            if video_url:
                if video_url.endswith('.m3u8') or video_url.endswith('.mp4'):
                    return {
                        "parse": 0,
                        "url": video_url,
                        "header": headers
                    }
                else:
                    return {
                        "parse": 1,
                        "url": video_url,
                        "header": headers
                    }
            
            # 方法3: 从iframe中提取
            iframe_src = self._extract_iframe_src(html)
            if iframe_src:
                return {
                    "parse": 1,
                    "url": iframe_src,
                    "header": headers
                }
            
            # 所有方法失败，返回页面让播放器自己解析
            return self._fallback_player(id)
            
        except Exception as e:
            print(f"播放器解析错误: {e}")
            return self._fallback_player(id)

    def _fallback_player(self, id):
        """播放器回退方案"""
        if not id.startswith('http'):
            url = f"{self.host}/play/{id}"
        else:
            url = id
        return {
            "parse": 1,
            "url": url,
            "header": {
                'User-Agent': self.def_headers['User-Agent'],
                'Referer': self.host + '/'
            }
        }

    # ==================== 核心解析方法 ====================
    def _extract_player_data(self, html):
        """
        从episodeManager的x-data中提取播放器数据
        这是4kvm网站的核心数据结构
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # 查找 episodeManager 组件
            episode_manager = soup.select_one('[x-data*="episodeManager"]')
            if not episode_manager:
                return None
            
            xdata = episode_manager.get('x-data', '')
            if not xdata:
                return None
            
            # 解析线路信息
            lines = []
            line_pattern = r"lineName\s*:\s*'([^']+)'.*?episodeCount\s*:\s*(\d+)"
            line_matches = re.findall(line_pattern, xdata)
            for name, count in line_matches:
                lines.append({"name": name, "count": int(count)})
            
            # 查找当前激活的剧集链接
            active_link = episode_manager.select_one('a.bg-indigo-600, a[class*="bg-indigo"]')
            if not active_link:
                active_link = episode_manager.select_one('a[data-episode]')
            
            if active_link:
                href = active_link.get('href', '')
                if href:
                    # 可能需要进一步请求获取视频地址
                    return {"url": self.host + href if not href.startswith('http') else href}
            
            # 尝试从script中查找player配置
            script_pattern = r'player_aaaa\s*=\s*(\{[^}]+\})'
            script_match = re.search(script_pattern, html, re.DOTALL)
            if script_match:
                try:
                    player_config = json.loads(script_match.group(1))
                    if 'url' in player_config:
                        return {"url": player_config['url']}
                except:
                    pass
            
            # 查找var player配置
            player_pattern = r'var\s+player\s*=\s*(\{[^}]+\})'
            player_match = re.search(player_pattern, html, re.DOTALL)
            if player_match:
                try:
                    player_config = json.loads(player_match.group(1))
                    if 'url' in player_config:
                        return {"url": player_config['url']}
                except:
                    pass
            
            return None
            
        except Exception as e:
            print(f"提取播放器数据错误: {e}")
            return None

    def _extract_video_from_script(self, html):
        """从script标签中提取视频URL"""
        try:
            # 查找各种可能的视频URL模式
            patterns = [
                r'url\s*:\s*[\'"]([^\'"]+\.(?:m3u8|mp4|flv))[\'"]',
                r'video\s*:\s*[\'"]([^\'"]+)[\'"]',
                r'src\s*:\s*[\'"]([^\'"]+\.(?:m3u8|mp4))[\'"]',
                r'["\']([^"\']*\.m3u8[^"\']*)["\']',
                r'["\']([^"\']*\.mp4[^"\']*)["\']',
            ]
            
            for pattern in patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    url = match.group(1)
                    if url.startswith('//'):
                        url = 'https:' + url
                    elif not url.startswith('http'):
                        url = self.host + '/' + url.lstrip('/')
                    return url
            
            return None
            
        except Exception as e:
            print(f"从脚本提取视频URL错误: {e}")
            return None

    def _extract_iframe_src(self, html):
        """提取iframe源地址"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            iframe = soup.find('iframe')
            if iframe:
                src = iframe.get('src', '')
                if src:
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif not src.startswith('http'):
                        src = self.host + '/' + src.lstrip('/')
                    return src
            return None
        except:
            return None

    def _parse_video_cards(self, soup, limit=None):
        """解析视频卡片列表"""
        video_list = []
        seen_ids = set()
        
        # 查找所有带data-vod-id的卡片
        cards = soup.select('div[data-vod-id]')
        if not cards:
            # 降级处理：查找链接
            cards = soup.select('a.block[href^="/play/"]')
        
        for card in cards:
            if limit and len(video_list) >= limit:
                break
            
            try:
                # 获取vod_id
                if card.name == 'div':
                    vod_id = card.get('data-vod-id', '').strip()
                    a_tag = card.select_one('a.block[href^="/play/"]')
                    if not a_tag:
                        continue
                    href = a_tag.get('href', '')
                    if not vod_id:
                        vod_id = href.replace('/play/', '').strip()
                else:
                    href = card.get('href', '')
                    vod_id = href.replace('/play/', '').strip()
                
                if not vod_id or vod_id in seen_ids:
                    continue
                seen_ids.add(vod_id)
                
                # 获取标题
                title_tag = card.select_one('h3.text-white') or card.select_one('h3')
                vod_name = title_tag.get_text(strip=True) if title_tag else vod_id
                
                # 获取图片
                vod_pic = ''
                img = card.select_one('img[data-src]') or card.select_one('img[src]')
                if img:
                    src = img.get('data-src', '') or img.get('src', '')
                    if src and not src.startswith('data:'):
                        vod_pic = self._fix_url(src)
                
                # 获取备注（评分/更新状态）
                vod_remarks = ''
                remark_elements = [
                    '.text-green-500',
                    '.text-yellow-400',
                    '.text-blue-500',
                    'span[class*="px-1.5"]',
                    '.absolute.top-2.right-2 span',
                ]
                for selector in remark_elements:
                    tag = card.select_one(selector)
                    if tag:
                        vod_remarks = tag.get_text(strip=True)
                        break
                
                video_list.append({
                    "vod_id": vod_id,
                    "vod_name": vod_name,
                    "vod_pic": vod_pic,
                    "vod_remarks": vod_remarks
                })
                
            except Exception as e:
                print(f"解析卡片错误: {e}")
                continue
        
        return video_list

    def _parse_episodes(self, soup, vod_id):
        """
        解析分集信息
        返回: (play_from_list, play_url_list)
        """
        play_from_list = []
        play_url_list = []
        
        try:
            # 查找 episodeManager 组件
            episode_manager = soup.select_one('[x-data*="episodeManager"]')
            
            if episode_manager:
                # 解析线路信息
                xdata = episode_manager.get('x-data', '')
                lines = []
                line_pattern = r"lineName\s*:\s*'([^']+)'.*?episodeCount\s*:\s*(\d+)"
                line_matches = re.findall(line_pattern, xdata)
                for name, count in line_matches:
                    lines.append({"name": name, "count": int(count)})
                
                # 获取所有剧集链接
                episode_links = episode_manager.select('a[data-episode]')
                
                # 按线路分组
                lines_eps = {}
                for a_tag in episode_links:
                    line = a_tag.get('data-line', '1')
                    ep = a_tag.get('data-episode', '')
                    href = a_tag.get('href', '')
                    if not href or not ep:
                        continue
                    
                    full_url = self._fix_url(href)
                    if line not in lines_eps:
                        lines_eps[line] = []
                    lines_eps[line].append((int(ep), full_url, a_tag.get_text(strip=True)))
                
                # 构建播放列表
                for line_key in sorted(lines_eps.keys()):
                    eps_list = sorted(lines_eps[line_key], key=lambda x: x[0])
                    
                    # 获取线路名称
                    line_name = f'线路{line_key}'
                    line_idx = int(line_key) - 1
                    if line_idx < len(lines) and lines[line_idx]['name']:
                        line_name = lines[line_idx]['name']
                    
                    # 构建剧集字符串
                    episode_strs = []
                    for ep_num, ep_url, ep_text in eps_list:
                        episode_strs.append(f"{ep_text}${ep_url}")
                    
                    if episode_strs:
                        play_from_list.append(line_name)
                        play_url_list.append('#'.join(episode_strs))
            
            # 如果没有找到分集，使用默认播放
            if not play_url_list:
                play_from_list.append('播放')
                play_url_list.append(f"播放${vod_id}")
            
        except Exception as e:
            print(f"解析分集错误: {e}")
            play_from_list = ['播放']
            play_url_list = [f"播放${vod_id}"]
        
        return play_from_list, play_url_list

    def _parse_title(self, soup, default=''):
        """解析标题"""
        selectors = [
            'h1.text-xl',
            'h1',
            'h2.text-lg',
            'h2',
            '.text-xl.font-bold',
        ]
        for sel in selectors:
            elem = soup.select_one(sel)
            if elem:
                return elem.get_text(strip=True)
        return default

    def _parse_poster(self, soup):
        """解析海报"""
        selectors = [
            'img.w-full[src]',
            'img.w-full[data-src]',
            'img.rounded-lg[src]',
            'img[src]',
            'img[data-src]',
        ]
        for sel in selectors:
            img = soup.select_one(sel)
            if img:
                src = img.get('src', '') or img.get('data-src', '')
                if src and not src.startswith('data:'):
                    return self._fix_url(src)
        return ''

    def _parse_info(self, soup):
        """解析导演、主演、简介"""
        director = ''
        actor = ''
        content = ''
        
        try:
            # 查找信息区域
            info_area = soup.select_one('.rounded-lg') or soup.select_one('div.grid')
            if info_area:
                text = info_area.get_text(' ', strip=True)
                
                # 导演
                dir_match = re.search(r'导演[：:]\s*([^主\n]+)', text)
                if dir_match:
                    director = dir_match.group(1).strip()
                
                # 主演
                act_match = re.search(r'主演[：:]\s*([^剧\n]+)', text)
                if act_match:
                    actor = act_match.group(1).strip()
                
                # 简介
                desc_match = re.search(r'(?:剧情)?简介[：:]\s*(.+?)(?:\n|$)', text)
                if desc_match:
                    content = desc_match.group(1).strip()
        except Exception as e:
            print(f"解析信息错误: {e}")
        
        return director, actor, content

    def _parse_pagecount(self, soup, current_page):
        """解析总页数"""
        pagecount = current_page
        
        try:
            # 方法1: 从"共X页"文本中提取
            page_text = soup.find(string=re.compile(r'共\s*\d+\s*页'))
            if page_text:
                nums = re.findall(r'\d+', page_text)
                if nums:
                    pagecount = int(nums[-1])
                    return pagecount
            
            # 方法2: 从分页链接中提取最大页码
            page_links = soup.select('a[href*="page="]')
            for a_tag in page_links:
                text = a_tag.get_text(strip=True)
                if text.isdigit():
                    pagecount = max(pagecount, int(text))
                    
        except Exception as e:
            print(f"解析页数错误: {e}")
        
        return pagecount

    def _get_dynamic_filters(self):
        """动态获取筛选条件"""
        try:
            url = f"{self.host}/filter?classify=1"
            html = self._fetch(url)
            if not html:
                return {}
            
            soup = BeautifulSoup(html, 'html.parser')
            filters = {}
            
            # 查找筛选区域
            filter_sections = soup.select('div.flex.flex-wrap.items-center.gap-2, div.flex.flex-wrap.gap-3')
            
            for section in filter_sections:
                links = section.select('a[href]')
                if len(links) < 2:
                    continue
                
                # 获取组名（从第一个"全部"链接中提取）
                first_text = links[0].get_text(strip=True)
                if '全部' not in first_text:
                    continue
                
                group_name = first_text.replace('全部', '').strip()
                if not group_name:
                    continue
                
                # 获取参数键
                param_key = None
                for a_tag in links[1:]:
                    href = a_tag.get('href', '')
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
                
                # 构建选项列表
                options = []
                for a_tag in links:
                    text = a_tag.get_text(strip=True)
                    href = a_tag.get('href', '')
                    parsed = urllib.parse.urlparse(href)
                    qs = urllib.parse.parse_qs(parsed.query)
                    
                    val = ''
                    if text.startswith('全部'):
                        val = ''
                    elif param_key in qs:
                        val = qs[param_key][0] if qs[param_key] else ''
                    
                    options.append({"n": text, "v": val})
                
                if options:
                    filters[param_key] = {
                        "key": param_key,
                        "name": group_name,
                        "value": options
                    }
            
            return filters
            
        except Exception as e:
            print(f"获取筛选条件错误: {e}")
            return {}

    def _fix_url(self, url):
        """修复URL格式"""
        if not url:
            return ''
        if url.startswith('//'):
            return 'https:' + url
        elif url.startswith('/'):
            return self.host + url
        elif not url.startswith('http'):
            return self.host + '/' + url
        return url

    def _fetch(self, url):
        """统一请求方法"""
        try:
            if not url.startswith('http'):
                url = self.host + url
            
            # 添加随机延迟
            time.sleep(random.uniform(0.3, 0.8))
            
            resp = self.fetch(url, headers=self.def_headers, verify=False)
            if resp and resp.status_code == 200:
                return resp.text
            elif resp and resp.status_code in [403, 503]:
                print(f"请求被拦截，状态码: {resp.status_code}")
                time.sleep(random.uniform(2, 4))
                resp = self.fetch(url, headers=self.def_headers, verify=False)
                if resp and resp.status_code == 200:
                    return resp.text
            return ''
        except Exception as e:
            print(f"请求失败: {e}")
            return ''

    # ==================== 其他必要方法 ====================
    def localProxy(self, param=''):
        return {}

    def isVideoFormat(self, url):
        """判断是否为直接视频格式"""
        if url and (url.endswith('.m3u8') or url.endswith('.mp4') or url.endswith('.flv')):
            return True
        return False

    def manualVideoCheck(self):
        """是否需要手动验证"""
        return False
