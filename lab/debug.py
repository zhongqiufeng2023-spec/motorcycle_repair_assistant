if __name__ == "__main__":
    tests = [
        ("真投诉", "你们这店太坑了,来回折腾三趟,退钱!"),
        ("真投诉", "买的刹车片装上就异响,什么破质量"),
        ("真投诉", "客服态度也太差了吧,一直推脱"),
        ("描述故障", "我的刹车失灵了,太危险了"),
        ("描述故障", "车子异响,烦死了"),
        ("描述故障", "发动机抖得厉害,是不是坏了"),
        ("中性提问", "火花塞的电极间隙是多少"),
        ("中性提问", "机油多久换一次"),
        ("中性提问", "Ninja 400 用什么型号火花塞"),
        ("正面", "谢谢,帮大忙了"),
        ("正面", "你们服务真不错"),
    ]
    for label, q in tests:
        q_vec = _embed_model.encode([q])['dense_vecs'][0]
        sims = [np.dot(q_vec, cv)/(np.linalg.norm(q_vec)*np.linalg.norm(cv)) for cv in _complaint_vectors]
        print(f"{max(sims):.3f}  [{label}] {q}")