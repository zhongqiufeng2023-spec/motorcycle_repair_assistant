from transformers import pipeline

# 首次运行会下载模型(~400MB)
clf = pipeline("sentiment-analysis", model="uer/roberta-base-finetuned-dianping-chinese")

tests = [
    # 真投诉(期望高分 negative)
    "你们这店太坑了,来回折腾三趟,退钱!",
    "买的刹车片装上就异响,什么破质量",
    "客服态度也太差了吧,一直推脱",
    # 描述故障(负面词多,但不是投诉)
    "我的刹车失灵了,太危险了",
    "车子异响,烦死了",
    "发动机抖得厉害,是不是坏了",
    # 中性提问
    "火花塞的电极间隙是多少",
    "机油多久换一次",
    "Ninja 400 用什么型号火花塞",
    # 正面
    "谢谢,帮大忙了",
    "你们服务真不错",
]

for t in tests:
    print(f"{t}\n  → {clf(t)}\n")