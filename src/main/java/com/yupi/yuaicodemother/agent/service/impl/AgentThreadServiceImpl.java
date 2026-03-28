package com.yupi.yuaicodemother.agent.service.impl;

import cn.hutool.core.bean.BeanUtil;
import cn.hutool.core.util.IdUtil;
import cn.hutool.core.util.StrUtil;
import com.mybatisflex.core.query.QueryWrapper;
import com.mybatisflex.spring.service.impl.ServiceImpl;
import com.yupi.yuaicodemother.constant.UserConstant;
import com.yupi.yuaicodemother.agent.model.dto.AgentThreadCreateRequest;
import com.yupi.yuaicodemother.agent.model.entity.AgentThread;
import com.yupi.yuaicodemother.agent.model.enums.AgentThreadStatusEnum;
import com.yupi.yuaicodemother.agent.model.vo.AgentThreadVO;
import com.yupi.yuaicodemother.exception.ErrorCode;
import com.yupi.yuaicodemother.exception.ThrowUtils;
import com.yupi.yuaicodemother.mapper.agent.AgentThreadMapper;
import com.yupi.yuaicodemother.model.entity.App;
import com.yupi.yuaicodemother.model.entity.User;
import com.yupi.yuaicodemother.service.AppService;
import com.yupi.yuaicodemother.agent.service.AgentThreadService;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;

import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;

@Service
public class AgentThreadServiceImpl extends ServiceImpl<AgentThreadMapper, AgentThread> implements AgentThreadService {

    @Resource
    private AppService appService;

    @Override
    public AgentThread createThread(AgentThreadCreateRequest request, User loginUser) {
        ThrowUtils.throwIf(request == null, ErrorCode.PARAMS_ERROR);
        Long appId = request.getAppId();
        ThrowUtils.throwIf(appId == null || appId <= 0, ErrorCode.PARAMS_ERROR, "应用 id 错误");
        ThrowUtils.throwIf(loginUser == null, ErrorCode.NOT_LOGIN_ERROR);
        assertAppAccess(appId, loginUser);

        long threadId = IdUtil.getSnowflakeNextId();
        AgentThread thread = AgentThread.builder()
                .id(threadId)
                .appId(appId)
                .userId(loginUser.getId())
                .title(StrUtil.blankToDefault(StrUtil.trim(request.getTitle()), null))
                .pythonSessionId(String.valueOf(threadId))
                .status(AgentThreadStatusEnum.ACTIVE.getValue())
                .lastMessageAt(LocalDateTime.now())
                .build();
        boolean saved = this.save(thread);
        ThrowUtils.throwIf(!saved, ErrorCode.OPERATION_ERROR, "创建知识问答线程失败");
        return thread;
    }

    @Override
    public List<AgentThreadVO> listThreads(Long appId, User loginUser) {
        ThrowUtils.throwIf(appId == null || appId <= 0, ErrorCode.PARAMS_ERROR, "应用 id 错误");
        ThrowUtils.throwIf(loginUser == null, ErrorCode.NOT_LOGIN_ERROR);
        assertAppAccess(appId, loginUser);

        QueryWrapper queryWrapper = QueryWrapper.create()
                .eq("app_id", appId)
                .eq("user_id", loginUser.getId())
                .eq("status", AgentThreadStatusEnum.ACTIVE.getValue())
                .orderBy("last_message_at", false)
                .orderBy("create_time", false);
        List<AgentThread> threadList = this.list(queryWrapper);
        List<AgentThreadVO> threadVOList = new ArrayList<>();
        for (AgentThread thread : threadList) {
            AgentThreadVO threadVO = new AgentThreadVO();
            BeanUtil.copyProperties(thread, threadVO);
            threadVOList.add(threadVO);
        }
        return threadVOList;
    }

    @Override
    public AgentThread getOwnedThread(Long threadId, User loginUser) {
        ThrowUtils.throwIf(threadId == null || threadId <= 0, ErrorCode.PARAMS_ERROR, "线程 id 错误");
        ThrowUtils.throwIf(loginUser == null, ErrorCode.NOT_LOGIN_ERROR);
        AgentThread thread = this.getById(threadId);
        ThrowUtils.throwIf(thread == null, ErrorCode.NOT_FOUND_ERROR, "线程不存在");
        ThrowUtils.throwIf(!loginUser.getId().equals(thread.getUserId()), ErrorCode.NO_AUTH_ERROR, "无权访问该线程");
        assertAppAccess(thread.getAppId(), loginUser);
        return thread;
    }

    @Override
    public boolean archiveThread(Long threadId, User loginUser) {
        AgentThread thread = getOwnedThread(threadId, loginUser);
        if (AgentThreadStatusEnum.ARCHIVED.getValue().equals(thread.getStatus())) {
            return true;
        }
        thread.setStatus(AgentThreadStatusEnum.ARCHIVED.getValue());
        thread.setUpdateTime(LocalDateTime.now());
        return this.updateById(thread);
    }

    @Override
    public AgentThread fillThreadTitleIfBlank(AgentThread thread, String firstMessage) {
        if (thread == null || StrUtil.isNotBlank(thread.getTitle()) || StrUtil.isBlank(firstMessage)) {
            return thread;
        }
        String normalized = StrUtil.replace(firstMessage.trim(), "\r", " ");
        normalized = StrUtil.replace(normalized, "\n", " ");
        String title = normalized.length() <= 40 ? normalized : StrUtil.subPre(normalized, 40);
        thread.setTitle(title);
        thread.setUpdateTime(LocalDateTime.now());
        this.updateById(thread);
        return thread;
    }

    private void assertAppAccess(Long appId, User loginUser) {
        App app = appService.getById(appId);
        ThrowUtils.throwIf(app == null, ErrorCode.NOT_FOUND_ERROR, "应用不存在");
        boolean isAdmin = UserConstant.ADMIN_ROLE.equals(loginUser.getUserRole());
        ThrowUtils.throwIf(!isAdmin && !loginUser.getId().equals(app.getUserId()), ErrorCode.NO_AUTH_ERROR, "无权访问该应用");
    }
}
