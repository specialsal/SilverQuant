# ProjectQ

## Intro

root 根目录下

* `manual_` 开头的手动执行的小工具
* `tick_` 开头的都是策略文件
    * `tick_accounts.py` 主要存放QMT账号和缓存路径相关的信息
        * 这个文件的改动可以不用在Github上同步
        *  节省Stash操作，之后可以直接Pull最新策略代码
        * 其他的tick文件主要关注点是策略内的参数调优
    * `tick_dk.py` 是低开策略
    * `tick_hma.py` 是HMA策略
    * `tick_sma.py` 是SMA策略
    
_cache是策略的临时缓存，配置在`tick_accounts.py`文件中

* `prod_` 开头的对应的是实盘环境
* `staging_` 开头对应的是模拟盘环境
