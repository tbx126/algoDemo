"""各标准评测器共用的执行锁：同一时间只运行一个评测，保证耗时与显存峰值的测量不被其他评测干扰"""
import threading

EVAL_LOCK = threading.Lock()
