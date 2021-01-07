import json
import pickle
import random
import time
from abc import ABC, abstractmethod
from datetime import datetime

import requests
from selenium import common
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.expected_conditions import presence_of_element_located
from selenium.webdriver.support.wait import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager


class Timer(object):
    def __init__(self, sleep_interval=0.5, buy_time='09:59:59.500'):
        # '2018-09-28 22:45:50.000'
        # buy_time = 2020-12-22 09:59:59.500
        localtime = time.localtime(time.time())

        buy_time_config = datetime.strptime(
            localtime.tm_year.__str__() + '-' + localtime.tm_mon.__str__() + '-' + localtime.tm_mday.__str__() + ' ' + buy_time,
            "%Y-%m-%d %H:%M:%S.%f")
        if time.mktime(localtime) < time.mktime(buy_time_config.timetuple()):
            self.buy_time = buy_time_config
        else:
            self.buy_time = datetime.strptime(
                localtime.tm_year.__str__() + '-' + localtime.tm_mon.__str__() + '-' + (
                        localtime.tm_mday + 1).__str__() + ' ' + buy_time,
                "%Y-%m-%d %H:%M:%S.%f")
        print("购买时间：{}".format(self.buy_time))

        self.buy_time_ms = int(time.mktime(self.buy_time.timetuple()) * 1000.0 + self.buy_time.microsecond / 1000)
        self.sleep_interval = sleep_interval

        self.diff_time = self.local_jd_time_diff()

    def jd_time(self):
        """
        从京东服务器获取时间毫秒
        :return:
        """
        url = 'https://a.jd.com//ajax/queryServerData.html'
        ret = requests.get(url).text
        js = json.loads(ret)
        return int(js["serverTime"])

    def local_time(self):
        """
        获取本地毫秒时间
        :return:
        """
        return int(round(time.time() * 1000))

    def local_jd_time_diff(self):
        """
        计算本地与京东服务器时间差
        :return:
        """
        return self.local_time() - self.jd_time()

    def start(self):
        print(f'正在等待到达设定时间:{self.buy_time}，本地时间为{self.local_time()}, jd时间为{self.jd_time()},'
              f' 检测本地时间与京东服务器时间误差为【{self.diff_time}】毫秒')
        wait_time = 1
        while True:
            # 本地时间减去与京东的时间差，能够将时间误差提升到0.1秒附近
            # 具体精度依赖获取京东服务器时间的网络时间损耗
            if self.local_time() - self.diff_time >= self.buy_time_ms:
                print('时间到达，开始执行……')
                break
            else:
                if wait_time % 100 == 0:
                    print('正在等待中...', f'还需等待{(self.buy_time_ms - (self.local_time() - self.diff_time)) / 1000}秒')
                time.sleep(self.sleep_interval)
            wait_time += 1


class BaseSpider(ABC):

    def __init__(self, base_url: str, login_url: str, verify_url: str, sleep_time: int = 3):
        self.base_url = base_url
        self.login_url = login_url
        self.verify_url = verify_url
        self.driver = self.get_chrome_driver()
        self.wait = WebDriverWait(self.driver, 0.3, 0.05)
        self.is_login = False
        self.sleep_time = sleep_time
        self.data_list = []

    def start(self):
        self.login_by_cookies()
        self.driver.get(self.base_url)
        self.run()
        self.close()

    @abstractmethod
    def run(self):
        pass

    def sleep(self):
        time.sleep(self.sleep_time)

    @staticmethod
    def get_chrome_driver() -> webdriver:
        options = webdriver.ChromeOptions()
        options.add_argument('--no-sandbox')
        # options.add_argument('--headless')  # 无头参数
        options.add_argument('--disable-gpu')
        # 關閉瀏覽器左上角通知提示
        prefs = {
            'profile.default_content_setting_values':
                {
                    'notifications': 2
                }
        }
        options.add_experimental_option('prefs', prefs)
        # 關閉'chrome目前受到自動測試軟體控制'的提示
        options.add_experimental_option('useAutomationExtension', False)
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        driver = webdriver.Chrome(ChromeDriverManager().install(), chrome_options=options)
        driver.maximize_window()
        driver.implicitly_wait(10)
        return driver

    def login_by_cookies(self):
        if self.load_cookie():
            return self
        return self.login()

    def login(self):
        print('开始进行人工登录')
        driver = self.driver
        if not self.is_login:
            driver.get(self.login_url)
        self.verify_login()
        return self

    def verify_login(self):
        wait_time = 0
        while True and not self.is_login:
            print(f'登录中...等待时间为{wait_time}s')
            time.sleep(5)
            wait_time = wait_time + 5
            if self.verify_url in self.driver.current_url and not self.driver.current_url == self.login_url:
                print('登录成功')
                self.is_login = True
                break
            if wait_time >= 300:
                raise Exception('登录失败')
        self.save_cookie()
        return self.is_login

    def save_cookie(self):
        cookie = self.driver.get_cookies()
        with open(self.__class__.__name__, 'wb') as f:
            f.write(pickle.dumps(cookie))

    def load_cookie(self):
        print('开始加载cookies信息')
        try:
            with open(self.__class__.__name__, 'rb') as f:
                cookie = pickle.load(f)
                if not cookie:
                    return False
        except FileNotFoundError as e:
            return False
        for cookies in cookie:
            if 'expiry' in cookies:
                del cookies['expiry']
            if 'domain' in cookie:
                del cookies['domain']
        self.driver.get(self.base_url)
        for i in cookie:
            self.driver.add_cookie(i)
        print("load over")
        self.driver.refresh()
        self.is_login = True
        return self

    def close(self):
        self.save_cookie()
        self.driver.close()
        self.driver.quit()
        self.is_login = False


class JdSpider(BaseSpider):

    def __init__(self, sleep_time: int = 3, item_id: int = 100012043978, buy_time='09:59:50.500'):
        super().__init__(base_url='http://jd.com', login_url='https://passport.jd.com/new/login.aspx',
                         verify_url='https://www.jd.com/', sleep_time=sleep_time)
        self.item_id = item_id
        self.item_url = f'https://item.jd.com/{item_id}.html'
        self.buy_time = buy_time

    def run(self):
        self.driver.get(self.item_url)
        Timer(buy_time=self.buy_time).start()
        try_time = 0
        while True:
            self.driver.get(self.item_url)
            first_result = self.wait.until(presence_of_element_located((By.ID, "btn-reservation")))
            text_content = first_result.get_attribute("textContent")
            if text_content in ['等待抢购', '开始预购', '等待预购', '等待预约', '开始预约']:
                print('还没开始，等待抢购!')
            else:
                try_time += 1
                try:
                    print('终于开始了，立即抢购!')
                    first_result.click()
                    first_result = self.wait.until(presence_of_element_located((By.CLASS_NAME, "checkout-submit")))
                    first_result.click()
                    print("提交订单！")
                    time.sleep(30)
                    break
                except common.exceptions.TimeoutException as e:
                    print(f'第{try_time}次没赶上-----------再试试!!!!!!!')
                    if try_time >= 30:
                        print('不试了, 明天再来')
                        break
            if try_time == 0:
                time.sleep(random.randint(1, 5) * 0.1)


if __name__ == '__main__':
    # 提前一直刷新页面
    dd = JdSpider(buy_time='09:59:53.500')
    dd.start()
