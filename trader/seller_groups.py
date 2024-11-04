from trader.seller_components import *


class GroupSellers:
    def __init__(self):
        pass

    def group_init(self, strategy_name, delegate, parameters):
        for parent in self.__class__.__bases__:
            if parent.__name__ != 'GroupSellers':
                parent.__init__(self, strategy_name, delegate, parameters)
        print('>> 初始化完成')

    def group_check_sell(self, code: str, quote: Dict, curr_date: str, curr_time: str, position: XtPosition,
                         held_day: int, max_price: Optional[float], history: Optional[pd.DataFrame]) -> bool:
        sold = False
        for parent in self.__class__.__bases__:
            if parent.__name__ != 'GroupSellers':
                if sold:
                    break
                else:
                    sold = parent.check_sell(self, code=code, quote=quote, curr_date=curr_date, curr_time=curr_time,
                                             position=position, held_day=held_day, max_price=max_price, history=history)
        return sold


class ClassicGroupSeller(GroupSellers, HardSeller, SwitchSeller, ReturnSeller):
    def __init__(self, strategy_name, delegate, parameters):
        super().__init__()
        self.group_init(strategy_name, delegate, parameters)

    def check_sell(self, code, quote, curr_date, curr_time, position, held_day, max_price, history):
        self.group_check_sell(code, quote, curr_date, curr_time, position, held_day, max_price, history)


class ShieldGroupSeller(GroupSellers, HardSeller, FallSeller, ReturnSeller):
    def __init__(self, strategy_name, delegate, parameters):
        super().__init__()
        self.group_init(strategy_name, delegate, parameters)

    def check_sell(self, code, quote, curr_date, curr_time, position, held_day, max_price, history):
        self.group_check_sell(code, quote, curr_date, curr_time, position, held_day, max_price, history)


class LTT2GroupSeller(GroupSellers, HardSeller, OpenDaySeller, SwitchSeller, ReturnSeller, CCISeller, MASeller):
    def __init__(self, strategy_name, delegate, parameters):
        super().__init__()
        self.group_init(strategy_name, delegate, parameters)

    def check_sell(self, code, quote, curr_date, curr_time, position, held_day, max_price, history):
        self.group_check_sell(code, quote, curr_date, curr_time, position, held_day, max_price, history)


class T3BLGroupSeller(GroupSellers, HardSeller, SwitchSeller, FallSeller, MASeller):
    def __init__(self, strategy_name, delegate, parameters):
        super().__init__()
        self.group_init(strategy_name, delegate, parameters)

    def check_sell(self, code, quote, curr_date, curr_time, position, held_day, max_price, history):
        self.group_check_sell(code, quote, curr_date, curr_time, position, held_day, max_price, history)


class CDBLGroupSeller(GroupSellers, HardSeller, SwitchSeller, FallSeller):
    def __init__(self, strategy_name, delegate, parameters):
        super().__init__()
        self.group_init(strategy_name, delegate, parameters)

    def check_sell(self, code, quote, curr_date, curr_time, position, held_day, max_price, history):
        self.group_check_sell(code, quote, curr_date, curr_time, position, held_day, max_price, history)
