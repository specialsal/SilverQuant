# 客户端安装说明

# 系统需求

> 至少是 Windows 系统，国内交易软件生态大都不支持 Mac 和 Linux

# 软件下载

> 下载 Github 桌面版
> 
> https://desktop.github.com/

> 下载 PyCharm CE for Windows（注意是免费版，不是Professional）
> 
> https://www.jetbrains.com/pycharm/download/?section=windows

> 下载国金证券 QMT（推荐国金证券的券商版 QMT，用其他券商QMT可以下载他们对应的券商版 QMT）
> 
> WinRAR下载 https://www.win-rar.com/start.html?&L=0
> 
> QMT 实盘 https://download.gjzq.com.cn/gjty/organ/gjzqqmt.rar
> 
> QMT 模拟 https://download.gjzq.com.cn/temp/organ/gjzqqmt_ceshi.rar

> 如果需要问财大模型相关功能，需要下载 Node.JS 版本大于v20
>
> https://nodejs.org/zh-cn

> 如果需要模拟盘先做策略测试，需要下载 掘金3 的仿真交易软件
> 
> https://www.myquant.cn/terminal


# 配置环境

克隆项目到本地

> 可以直接在Github Desktop里克隆
> 
> 也可以直接在终端输入 gh repo clone silver6wings/SilverQuant 然后在Github Desktop里打开

用 PyCharm 打开刚才 clone 的 SilverQuant 文件夹：主菜单 File > Open，选择 SilverQuant 文件夹

安装 Python 3.10 版本
 
> 1. 可以打开PyCharm在IDE里安装
> 2. 也可以直接去Python官网下载：https://www.python.org/downloads/release/python-31010/

安装对应的包
 
> 在PyCharm里安装依赖，打开Terminal输入：pip install -r requirements.txt

如果安装慢可以使用镜像，在指令后加 ` -i [镜像网址]` 

> 1) https://pypi.tuna.tsinghua.edu.cn/simple/ 清华大学
> 2) https://pypi.mirrors.ustc.edu.cn/simple/ 中国科技大学
> 3) http://pypi.mirrors.ustc.edu.cn/simple/ 中国科学技术大学
> 4) http://mirrors.aliyun.com/pypi/simple/ 阿里云

# 启动程序

启动QMT交易软件

> 启动券商版迅投QMT的（勾选）极简模式，确认左下角数据源的链接状态正常

配置Credentials

> 复制项目根目录下的 credentials_sample.py，改名为credential.py并填入自己的参数
> 
> 1. AUTHENTICATION 是远程策略获取推送服务的密钥，其他策略不需要可置空
> 2. CACHE_BASE_PATH 是本地策略缓存文件夹路径，可不用修改
> 3. QMT_开头的两项是账户相关，需要股票账户id和QMT安装位置，找不到userdata_mini文件夹需要先启动QMT相关
> 4. DING_开头的两项是群通知相关，钉钉通知需要建群，然后建立机器人获取Webhook URL
> 5. GM_开头的两项是模拟盘相关，模拟盘需要自行获取掘金的Secret Tokens

启动脚本

> PyCharm 中打开 SilverQuant 项目根目录
> 
> 1. 找到 run_xxxxxx.py 文件，根目录下
> 2. 找到 IS_PROD = False 代码处，将 False 改为 True 切换成实盘
> 3. 确认 QMT 交易软件正在运行
> 4. 启动 run_xxxxxx.py 文件，点击绿色小三角

参数配置

> 修改参数后需要重新启动程序生效

Pool Parameters 股票池相关的参数

> * white_indexes 白名单指数列表，买点会选择这些指数的成分券
> * black_queries 黑名单问财语句，会拉黑当天问财语句里选出来的这些股票绝对不买

Buy Parameters 买点相关的参数

> * time_ranges 扫描买点时间段，如果不用买点只用卖点的话可以改成 time_ranges = []
> * interval 扫描买点间隔，取60的约数：1-6, 10, 12, 15, 20, 30
> * order_premium 保证市价单成交的溢价，单位（元）
> 
> 其他看代码中详细说明

Sell Parameters 卖点相关的参数

> * time_ranges 扫描卖点时间段，如果不用买点只用卖点的话可以改成 time_ranges = []
> * interval 扫描卖点间隔，取60的约数：1-6, 10, 12, 15, 20, 30
> * order_premium 保证市价单成交的溢价，单位（元）
> 
> 其他看代码中详细说明
 
# 注意事项

> 1. 尽量保持空仓开始，如果账户预先有股票则由于程序未记录持仓历史导致无法正确卖出
> 2. 确保手动买入的时候正在开启程序，程序也会自动记录主观买入的持仓
> 3. 使用过程，需要保证每日开市时开启程序，否则无法正确记录持仓时间和历史的最高价导致卖出无法符合预期
> 4. 可以在 CACHE_BASE_PATH对应的目录里查看缓存是否正确，关键文件有两个
>    * `held_days.json` 里记录的是持仓天数
>    * `max_price.json` 里记录的是历史最高价格

# 申请通知机器人

钉钉机器人通知可以自行建立，首先拉至少三人创建一个普通群

> 1. 群设置里：机器人 -> 添加机器人 -> 自定义机器人 -> 添加
> 2. 安全设置：加签 获取 DING_SECRET
> 3. 勾选“同意xxxx”，并下一步
> 4. Webhook栏，点击复制，获取 DING_TOKENS
> 5. 配置到credentials.py

# 常见问题 Q & A

> About setup
> 
> 启动之前最好重启一下系统刷新所有的软件配置
> 
> About akshare
> 
> 由于akshare会去各个官方网站抓取公开数据，网站改版会导致爬虫失效，akshare更新比较及时，更新akshare版本到最新会解决一些问题
>
>   * pip install akshare --upgrade
> 
> About pywencai
> 
> pywencai的原理是去 https://www.iwencai.com/ 抓取数据，所以记得一定要先安装 Node.js
> 
> 其次检查自己的 prompt 能不能在网页上搜到票
