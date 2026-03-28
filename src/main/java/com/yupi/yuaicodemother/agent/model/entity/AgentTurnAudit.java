package com.yupi.yuaicodemother.agent.model.entity;

import com.mybatisflex.annotation.Column;
import com.mybatisflex.annotation.Id;
import com.mybatisflex.annotation.KeyType;
import com.mybatisflex.annotation.Table;
import com.mybatisflex.core.keygen.KeyGenerators;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.io.Serial;
import java.io.Serializable;
import java.time.LocalDateTime;

/**
 * Agent turn audit entity.
 */
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Table("agent_turn_audit")
public class AgentTurnAudit implements Serializable {

    @Serial
    private static final long serialVersionUID = 1L;

    /**
     * Id.
     */
    @Id(keyType = KeyType.Generator, value = KeyGenerators.snowFlakeId)
    private Long id;

    /**
     * Thread id.
     */
    @Column("thread_id")
    private Long threadId;

    /**
     * Trace id.
     */
    @Column("trace_id")
    private String traceId;

    /**
     * Request text.
     */
    @Column("request_text")
    private String requestText;

    /**
     * Audit status.
     */
    private String status;

    /**
     * Error code.
     */
    @Column("error_code")
    private String errorCode;

    /**
     * Latency in milliseconds.
     */
    @Column("latency_ms")
    private Long latencyMs;

    /**
     * Metrics JSON.
     */
    @Column("metrics_json")
    private String metricsJson;

    /**
     * Create time.
     */
    @Column("create_time")
    private LocalDateTime createTime;
}
