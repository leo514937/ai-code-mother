package com.yupi.yuaicodemother.agent.service.impl;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.json.JSONUtil;
import com.mybatisflex.core.paginate.Page;
import com.mybatisflex.core.query.QueryWrapper;
import com.mybatisflex.spring.service.impl.ServiceImpl;
import com.yupi.yuaicodemother.agent.model.entity.AgentMessage;
import com.yupi.yuaicodemother.agent.model.vo.AgentMessageVO;
import com.yupi.yuaicodemother.exception.ErrorCode;
import com.yupi.yuaicodemother.exception.ThrowUtils;
import com.yupi.yuaicodemother.mapper.agent.AgentMessageMapper;
import com.yupi.yuaicodemother.agent.service.AgentMessageService;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

@Service
public class AgentMessageServiceImpl extends ServiceImpl<AgentMessageMapper, AgentMessage> implements AgentMessageService {

    @Override
    public List<AgentMessageVO> listThreadMessages(Long threadId, int pageSize, LocalDateTime lastCreateTime) {
        ThrowUtils.throwIf(threadId == null || threadId <= 0, ErrorCode.PARAMS_ERROR, "线程 id 错误");
        ThrowUtils.throwIf(pageSize <= 0 || pageSize > 100, ErrorCode.PARAMS_ERROR, "pageSize 必须在 1-100 之间");

        QueryWrapper queryWrapper = QueryWrapper.create()
                .eq("thread_id", threadId)
                .orderBy("create_time", false);
        if (lastCreateTime != null) {
            queryWrapper.lt("create_time", lastCreateTime);
        }
        Page<AgentMessage> page = this.page(Page.of(1, pageSize), queryWrapper);
        List<AgentMessage> records = new ArrayList<>(page.getRecords());
        Collections.reverse(records);

        List<AgentMessageVO> messageVOList = new ArrayList<>();
        for (AgentMessage record : records) {
            AgentMessageVO messageVO = new AgentMessageVO();
            BeanUtil.copyProperties(record, messageVO);
            messageVOList.add(messageVO);
        }
        return messageVOList;
    }

    @Override
    public int getNextSeq(Long threadId) {
        Page<AgentMessage> page = this.page(Page.of(1, 1), QueryWrapper.create()
                .eq("thread_id", threadId)
                .orderBy("seq", false));
        if (page.getRecords().isEmpty()) {
            return 0;
        }
        Integer seq = page.getRecords().get(0).getSeq();
        return seq == null ? 0 : seq;
    }

    @Override
    public AgentMessage saveMessage(Long threadId, String turnId, String role, String eventType, String contentText, Object payload, int seq) {
        AgentMessage message = AgentMessage.builder()
                .threadId(threadId)
                .turnId(turnId)
                .role(role)
                .eventType(eventType)
                .contentText(contentText)
                .payloadJson(payload == null ? null : JSONUtil.toJsonStr(payload))
                .seq(seq)
                .build();
        boolean saved = this.save(message);
        ThrowUtils.throwIf(!saved, ErrorCode.OPERATION_ERROR, "保存知识问答消息失败");
        return message;
    }
}
