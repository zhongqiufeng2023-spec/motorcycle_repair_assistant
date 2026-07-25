package com.moto.business.config;

import org.springframework.boot.CommandLineRunner;
import org.springframework.core.annotation.Order;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Component;

import java.util.List;

/**
 * 建 JPA 表达不了的数据库约束。目前只有一条:同一订单同时只能有一张待审(PENDING)退款工单。
 *
 * <p><b>为什么要这条约束</b>:agent 的 action_node 里含 interrupt(澄清追问),
 * 而 LangGraph 的 interrupt 恢复是【整个节点从头重放】——排在 interrupt 之前的
 * request_refund 会被再执行一次,同一订单开出两张 PENDING 工单。
 * 这是一期"真正的写操作必须放在 interrupt 之后"那条教训换了个马甲:
 * 写操作从"执行退款"变成了"开工单",位置却跑到了挂起点前面。
 *
 * <p><b>为什么约束必须落在数据库</b>:agent 侧记不住任何事 —— 被 interrupt 打断时
 * 节点根本没 return 过,state 补丁没提交、局部变量随重放清零。能跨重放记住事情的,
 * 只有重放管不到的地方,也就是这个库。这也符合"业务规则的唯一权威在业务系统"。
 *
 * <p><b>为什么不写在实体的 @Table(indexes=...) 里</b>:那里只能声明普通索引或
 * 全列唯一索引,表达不了【带条件的部分唯一索引】。而这里要的正是带条件那种 ——
 * 工单被驳回后用户应该还能再申请,所以唯一性只约束 status='PENDING' 的行。
 *
 * <p><b>为什么不是 service 里"先查后插"</b>:那有 TOCTOU 竞态(两个请求同时查、
 * 都没查到、都插入)。service 里那一查是省一次异常的快路径,真兜底是这个索引。
 *
 * <p>{@code IF NOT EXISTS} = 幂等,重启不重复建(同 DataSeeder 的纪律)。
 * 生产应换 Flyway/Liquibase 迁移,这里跟 ddl-auto=update 保持同一档次的轻量。
 */
@Component
@Order(0)   // 先于 DataSeeder:约束就位再灌数据
public class SchemaGuards implements CommandLineRunner {

    private static final String INDEX_NAME = "uniq_pending_ticket_per_order";

    private static final String CREATE_INDEX = """
            CREATE UNIQUE INDEX IF NOT EXISTS %s
              ON refund_tickets (order_id)
              WHERE status = 'PENDING'
            """.formatted(INDEX_NAME);

    private final JdbcTemplate jdbc;

    public SchemaGuards(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public void run(String... args) {
        try {
            jdbc.execute(CREATE_INDEX);
            System.out.println("[SchemaGuards] 唯一索引 " + INDEX_NAME + " 就位(同订单只允许一张待审工单)");
        } catch (Exception e) {
            // 建不上几乎只有一个原因:库里已经躺着重复的 PENDING 工单(正是这个 bug 的历史遗留)。
            // 不静默跳过——那等于悄悄失去兜底还以为有;也不让整个业务系统起不来——开发库的
            // 脏数据不该拖垮服务。报清楚是哪些订单、附上能直接执行的清理 SQL,让报错自己当说明书。
            System.err.println("[SchemaGuards] ⚠ 唯一索引 " + INDEX_NAME + " 建立失败:" + e.getMessage());
            reportDuplicates();
        }
    }

    /** 诊断:列出违反约束的订单,并给出清理 SQL(只留每个订单最早那张待审单)。 */
    private void reportDuplicates() {
        try {
            List<String> dups = jdbc.queryForList("""
                    SELECT order_id || ' → ' || COUNT(*) || ' 张待审'
                      FROM refund_tickets
                     WHERE status = 'PENDING'
                     GROUP BY order_id
                    HAVING COUNT(*) > 1
                    """, String.class);
            if (dups.isEmpty()) {
                System.err.println("[SchemaGuards] 未发现重复待审工单,失败另有原因,见上面的报错。");
                return;
            }
            System.err.println("[SchemaGuards] 重复的待审工单:" + dups);
            System.err.println("""
                    [SchemaGuards] 清理后重启即可(每个订单只留最早那张):
                      DELETE FROM refund_tickets t
                       WHERE t.status = 'PENDING'
                         AND t.id > (SELECT MIN(x.id) FROM refund_tickets x
                                      WHERE x.order_id = t.order_id AND x.status = 'PENDING');""");
        } catch (Exception diagFailed) {
            System.err.println("[SchemaGuards] 诊断查询也失败了:" + diagFailed.getMessage());
        }
    }
}
