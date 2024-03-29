from selenium import webdriver
import os
import json
import requests
from requests.cookies import RequestsCookieJar
from bs4 import BeautifulSoup
from pprint import pprint
import time
from random import randint
import imageio
import zipfile
import shutil

TRAN_TABLE = str.maketrans('', '', r'/\*:?|<>"') # 替换非法字符的表

def get_url(url, headers=0):
	'''
	请求一个url，返回内容。之所以用这个函数是为了配合出错后重试的函数使用。因为默认的requests最大重试次数不够用
	'''
	if headers != 0:
		res = session.get(url, headers=headers, timeout=1)
	else:
		res = session.get(url, timeout=1)
	return res

def restart_if_failed(func, max_tries, args=(), kwargs={}, secs=120, sleep=5):
	'''
	当出错时重新运行某个函数,直到在超出时间或者达到最大重试次数
	'''
	import traceback
	from collections import deque
	
	dq = deque(maxlen=max_tries)
	while True:
		dq.append(time.time())
		try:
			res = func(*args, **kwargs)
		except:
			traceback.print_exc()
			if len(dq) == max_tries and time.time() - dq[0] < secs:
				break
			if sleep is not None:
				time.sleep(sleep)
		else: # 不出错的时候执行这个else语句
			break
	return res

def read_cookie():
	'''
	读取cookies
	之所以将获取和读取cookies分开写
	主要是节省时间，一次获取保存以后直接读取即可
	'''
	jar = RequestsCookieJar()
	with open('pixiv_cookies.txt', 'r') as fp:
		cookies = json.load(fp)
		for cookie in cookies:
			jar.set(cookie['name'], cookie['value'])
	return jar
	
def get_artist_information(artist_rest):
	'''
	返回一个三个list，分别是画师的昵称和id，还有包含作者所有作品信息的url
	'''
	artist_name_list = []
	artist_id_list = []
	ajax_url_list = []
	headers = {
			'referer': 'https://accounts.pixiv.net/login',
			'origin': 'https://accounts.pixiv.net',
			'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
				 'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'}
	res = session.get(f'https://www.pixiv.net/bookmark.php?type=user&rest={artist_rest}', headers=headers, timeout=1) # 获取指定类型画师信息
	res_bs = BeautifulSoup(res.text, 'html.parser') 
	if res_bs.find('div', attrs={'class': '_pager-complex'}) != None:
		max_page = int(res_bs.find('div', attrs={'class': '_pager-complex'}).find_all('li')[-2].text) # 获取最大页码数，最大页码是在倒数第二的li里
	else:
		max_page = 1
	for i in range(1, max_page + 1): # 获取画师信息
		url = f'https://www.pixiv.net/bookmark.php?type=user&rest={artist_rest}&p={i}' 
		res = session.get(url, headers=headers, timeout=1)
		res_bs = BeautifulSoup(res.text, 'html.parser') # 构造bs对象
		artist_list = res_bs.find('section', id='search-result').find_all('div', attrs={'class': 'userdata'})
		for item in artist_list:
			artist_id_list.append(item.a['data-user_id'])
			artist_name_list.append(item.a['data-user_name'].translate(TRAN_TABLE))
			ajax_url_list.append('https://www.pixiv.net/ajax/user/{}/profile/all'.format(item.a['data-user_id']))
			

	print('已获取所有画师信息')
	return artist_name_list, artist_id_list, ajax_url_list

def get_id_group_list(ajax_url, artist_id):
	'''
	获取画师所有作品的id，从大到小排序并分组后返回一个嵌套的list。形如[[],[]]
	'''
	referer_url = 'https://www.pixiv.net/member.php?id=' + str(artist_id)
		# print(referer_url)
	headers = {
		'referer': referer_url,
		'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
				'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'}
	try:
		ajax_html = get_url(ajax_url, headers=headers) # 获取作品url,返回作家所有作品相关信息的json。其中有价值的信息是作品id
		temp_id_dict = json.loads(ajax_html.text)
	except:
		ajax_html = restart_if_failed(get_url, 20, (ajax_url, headers))
		temp_id_dict = json.loads(ajax_html.text)
	print('拿到画家作品数据')
	illusts_dict = temp_id_dict['body']['illusts']
	manga_dict = temp_id_dict['body']['manga']
	# 判断作者是否有漫画作品,有就合并到一块，没有就用illusts_dict
	if len(manga_dict) == 0:
		work_dict = dict(illusts_dict)
	else:
		work_dict = dict(illusts_dict, **manga_dict)
	
	# 获取作品的id
	work_id_list = list(work_dict.keys())
	work_id_list.sort() # 对id从小到大排序
	work_id_list = work_id_list[::-1] # 让id从大到小排序
	# 每组图片48个
	limit_num = 48
	id_group_list = [work_id_list[i:i+limit_num] for i in range(0, len(work_id_list), limit_num)] # 分组，每个元素是一个list
	return id_group_list

def get_work_list(id_group, artist_id, page_count):
	'''
	接受一个作品id分组，作者id, 构造url请求后解析信息，返回一个作品的list，里面每一个元素都是一个包含相信作品信息的dict
	'''
	ids_big = 'https://www.pixiv.net/ajax/user/{}/profile/illusts?'.format(artist_id)
	for id in id_group:
		ids = 'ids%5B%5D=' + id + '&'
		ids_big += ids
	work_url = ids_big + '&work_category=illust&is_first_page=' + str(page_count) # 构造请求图片的url
	
	# 发起ajax请求去获取作品详细信息
	print('第 ',page_count,'页')
	print(work_url)
	try:
		res = get_url(work_url)
		res_dict = json.loads(res.text) # 反序列化为dict
	except:
		res = restart_if_failed(get_url, 20, (work_url,)) # 单个元素要传元组应该加上,
		res_dict = json.loads(res.text) # 反序列化为dict
	work_list = res_dict['body']['works'].values() # 获取作品信息，得到list,其中每个元素是一个dict
	return work_list

def download_picture():
	'''
	解析数据传给下载函数下载
	'''
	try:
		artist_name_list, artist_id_list, ajax_url_list = get_artist_information(artist_rest)
	except:
		artist_name_list, artist_id_list, ajax_url_list = restart_if_failed(get_artist_information, 20 ,(artist_rest,))
	# name_count = 0
	# artist_id_count = 0
	name_count = artist_id_count = check_artist(artist_name_list)
	
	
	
	for i in range(name_count,len(ajax_url_list)): # 遍历每一个画师作品
		ajax_url = ajax_url_list[i]
		setup_artist(artist_name_list[name_count])
		artist_name = artist_name_list[name_count] # 获取画师名字
		artist_id = artist_id_list[artist_id_count] # 获取画师id
		id_group_list = get_id_group_list(ajax_url, artist_id)
		print('画师: ', artist_name, '作品', len(id_group_list), '页')
		page_count = 0
		for id_group in id_group_list:
			work_list = get_work_list(id_group, artist_id, page_count)
			page_count += 1
			for work in work_list:
				# 获取作品tile和缩略图url和页数
				#illustType表示图片的类型。0是一张图。1是多图，2是动图
				title = work['title']
				pic_url = work['url']
				pic_id = work['illustId']
				pic_num = work['pageCount']
				pic_illustType = work['illustType']
				pic_url = pic_url.replace('c/250x250_80_a2/', '').replace('square1200', 'master1200')
				try:
					download_pic(title, pic_id, pic_url, artist_name, pic_num, pic_illustType) # 调用下载函数
				except:
					restart_if_failed(download_pic, 20, (title, pic_id, pic_url, artist_name, pic_num, pic_illustType)) # 下载失败的时候重试
		name_count += 1
		artist_id_count += 1
		print(artist_name, '完成')
	clear_artist()
	print('已完成所有任务')

def download_pic(title, pic_id, pic_url, artist_name, pic_num, pic_illustType):
	'''
	下载图片,遇到动图则调用动图处理函数，多图发生错误时则删除以前多余图片
	'''
	os.makedirs(artist_name, exist_ok=True) # 创建画师名字的文件夹
	referer_url = 'https://www.pixiv.net/artworks/' + str(pic_id)
	title = title.translate(TRAN_TABLE)
	if pic_illustType != 2:
		# 构造一下header头
		headers = {
			'referer': referer_url,
			'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
				'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'}
		
		if pic_num == 1:
			time.sleep(randint(5,10)) # 暂停一下避免速度过快被封禁
			print('当前图片url: ', pic_url)
			r = session.get(pic_url, headers=headers, timeout=1) # 获取图片
			# 递归检查图片是否已经存在
			while os.path.isfile(f'{artist_name}/' + title + '.jpg'):
				title = title + '-1'
			with open(f'{artist_name}/' + title + '.jpg', 'wb') as fp:
				fp.write(r.content)
		else:
			try: # 处理图片重复
				pic_title_list = []	# 存储已经生成的图片名，如果报错需要根据图片名将图片逐个删除
				for i in range(pic_num):
					time.sleep(randint(5, 10)) # 暂停避免爬太快被封
					target_title = title + str(i)
					while os.path.isfile(f'{artist_name}/' + target_title + '.jpg'):
						target_title += '-1'
					target_url = pic_url.replace('p0', f'p{i}') # 替换目标url
					print('当前图片url: ', target_url)
					r = session.get(target_url, headers=headers, timeout=1)
					with open(f'{artist_name}/' + target_title + '.jpg', 'wb') as fp:
						fp.write(r.content)
					pic_title_list.append(target_title)
			except:
				for pic_title in pic_title_list:
					os.remove(f'{artist_name}/' + pic_title + '.jpg')
				raise ValueError('pic download error')
	else:
		time.sleep(randint(5, 10)) # 暂停避免爬太快被封
		get_gif(artist_name, title, pic_id, referer_url)

def get_gif(artist_name, title, pic_id, referer_url):
	'''
	处理动图的情况，下载图片压缩包，在本地合成动图
	'''
	file_name_list = []
	frame_list = []
	print('正在处理动图')
	url = f'https://www.pixiv.net/ajax/illust/{pic_id}/ugoira_meta'
	headers = {
			'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) '
				'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/56.0.2924.87 Safari/537.36'}
	res = session.get(url, headers=headers, timeout=1)
	res_obj = json.loads(res.text)
	delay = res_obj['body']['frames'][0]['delay']
	originalSrc = res_obj['body']['originalSrc']
	headers['referer'] = referer_url
	res = session.get(originalSrc, headers=headers, timeout=1) # 请求原图的压缩包，返回的是静态图的zip文件，需要自己处理合成为gif
	with open('temp.zip', 'wb') as fp:
		fp.write(res.content)
	zip_obj = zipfile.ZipFile('temp.zip', 'r')
	for file_name in zip_obj.namelist():
		file_name_list.append(file_name)
		zip_obj.extract(file_name)
	zip_obj.close() # 关闭zip文件
	# 合成gif图片
	for file_name in file_name_list:
		frame_list.append(imageio.imread(file_name))
	while os.path.isfile(f'{artist_name}/' + title + '.gif'):
		title += '-1'
	imageio.mimsave(f'{artist_name}/' + title + '.gif', frame_list, 'GIF', duration=delay / 1000)

	for file_name in file_name_list:
		os.remove(file_name)
	os.remove('temp.zip')

def setup_artist(artist_name):
	'''
	保存当前下载图片的artist_name
	'''
	with open(f'{artist_rest}_artist_name.txt', 'w') as fp:
		fp.write(artist_name)

def check_artist(artist_name_list):
	'''
	检查任务未完成，给用户选择任务开始的方式
	'''
	if os.path.isfile(f'{artist_rest}_artist_name.txt'):
		choose_num = int(input('发现未完成任务，继续任务输入1，重新开始输入2：'))
		if choose_num == 1:
			with open(f'{artist_rest}_artist_name.txt', 'r') as fp:
				artist_name = fp.readline()
				os.makedirs(artist_name, exist_ok=True)
				shutil.rmtree(artist_name)
				return artist_name_list.index(artist_name)
	for artist_name in artist_name_list:
		try:
			shutil.rmtree(artist_name)
		except:
			pass
	return 0

def clear_artist():
	'''
	任务完成后删除保存artist_name的txt文件
	'''
	if os.path.isfile(f'{artist_rest}_artist_name.txt'):
		os.remove(f'{artist_rest}_artist_name.txt')

if __name__ == '__main__':
	proxy = {
			'http' : '127.0.0.1:1080',
			'https' : '127.0.0.1:1080'
	}
	session = requests.Session()	# 定义并配置session对象
	session.proxies = proxy
	cookies = read_cookie()
	session.cookies = cookies
	choose_num = int(input('输入1抓取公开的画师，输入2抓取隐藏画师：'))
	artist_rest = 'show' if choose_num == 1 else 'hide'
	download_picture()