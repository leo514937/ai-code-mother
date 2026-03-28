package com.yupi.yuaicodemother.agent.controller;

import cn.hutool.core.bean.BeanUtil;
import com.yupi.yuaicodemother.agent.config.AgentFeatureProperties;
import com.yupi.yuaicodemother.agent.convert.PythonAgentEventConverter;
import com.yupi.yuaicodemother.agent.model.dto.AgentMessageStreamRequest;
import com.yupi.yuaicodemother.agent.model.dto.AgentThreadCreateRequest;
import com.yupi.yuaicodemother.agent.model.entity.AgentThread;
import com.yupi.yuaicodemother.agent.model.enums.AgentEventTypeEnum;
import com.yupi.yuaicodemother.agent.model.vo.AgentMessageVO;
import com.yupi.yuaicodemother.agent.model.vo.AgentThreadVO;
import com.yupi.yuaicodemother.agent.service.AgentGatewayService;
import com.yupi.yuaicodemother.agent.service.AgentMessageService;
import com.yupi.yuaicodemother.agent.service.AgentThreadService;
import com.yupi.yuaicodemother.common.BaseResponse;
import com.yupi.yuaicodemother.common.ResultUtils;
import com.yupi.yuaicodemother.exception.BusinessException;
import com.yupi.yuaicodemother.exception.ErrorCode;
import com.yupi.yuaicodemother.exception.ThrowUtils;
import com.yupi.yuaicodemother.model.entity.User;
import com.yupi.yuaicodemother.ratelimter.annotation.RateLimit;
import com.yupi.yuaicodemother.ratelimter.enums.RateLimitType;
import com.yupi.yuaicodemother.service.UserService;
import jakarta.annotation.Resource;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

import java.time.LocalDateTime;
import java.util.List;

@RestController
@RequestMapping("/agent")
public class AgentThreadController {

    @Resource
    private AgentThreadService agentThreadService;

    @Resource
    private AgentMessageService agentMessageService;

    @Resource
    private AgentGatewayService agentGatewayService;

    @Resource
    private UserService userService;

    @Resource
    private AgentFeatureProperties agentFeatureProperties;

    @Resource
    private PythonAgentEventConverter pythonAgentEventConverter;

    @GetMapping("/threads")
    public BaseResponse<List<AgentThreadVO>> listThreads(@RequestParam Long appId, HttpServletRequest request) {
        ensureSidebarEnabled();
        User loginUser = userService.getLoginUser(request);
        return ResultUtils.success(agentThreadService.listThreads(appId, loginUser));
    }

    @GetMapping("/sidebar/enabled")
    public BaseResponse<Boolean> getSidebarEnabled() {
        return ResultUtils.success(agentFeatureProperties.getSidebar().isEnabled());
    }

    @PostMapping("/threads")
    public BaseResponse<AgentThreadVO> createThread(@RequestBody AgentThreadCreateRequest createRequest,
                                                    HttpServletRequest request) {
        ensureSidebarEnabled();
        User loginUser = userService.getLoginUser(request);
        AgentThread thread = agentThreadService.createThread(createRequest, loginUser);
        AgentThreadVO threadVO = new AgentThreadVO();
        BeanUtil.copyProperties(thread, threadVO);
        return ResultUtils.success(threadVO);
    }

    @GetMapping("/threads/{threadId}/messages")
    public BaseResponse<List<AgentMessageVO>> listThreadMessages(@PathVariable Long threadId,
                                                                 @RequestParam(defaultValue = "50") int pageSize,
                                                                 @RequestParam(required = false) LocalDateTime lastCreateTime,
                                                                 HttpServletRequest request) {
        ensureSidebarEnabled();
        User loginUser = userService.getLoginUser(request);
        agentThreadService.getOwnedThread(threadId, loginUser);
        return ResultUtils.success(agentMessageService.listThreadMessages(threadId, pageSize, lastCreateTime));
    }

    @PostMapping("/threads/{threadId}/archive")
    public BaseResponse<Boolean> archiveThread(@PathVariable Long threadId, HttpServletRequest request) {
        ensureSidebarEnabled();
        User loginUser = userService.getLoginUser(request);
        return ResultUtils.success(agentThreadService.archiveThread(threadId, loginUser));
    }

    @PostMapping(value = "/threads/{threadId}/messages/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    @RateLimit(limitType = RateLimitType.USER, rate = 5, rateInterval = 60, message = "Agent sidebar requests are too frequent")
    public Flux<ServerSentEvent<String>> streamMessage(@PathVariable Long threadId,
                                                       @RequestBody AgentMessageStreamRequest messageStreamRequest,
                                                       HttpServletRequest request) {
        return Flux.defer(() -> {
                    ensureSidebarEnabled();
                    ThrowUtils.throwIf(messageStreamRequest == null, ErrorCode.PARAMS_ERROR);
                    User loginUser = userService.getLoginUser(request);
                    return agentGatewayService.streamMessage(threadId, messageStreamRequest.getContent(), loginUser);
                })
                .onErrorResume(throwable -> Flux.just(
                        pythonAgentEventConverter.toServerSentEvent(
                                pythonAgentEventConverter.buildEvent(
                                        threadId,
                                        null,
                                        null,
                                        AgentEventTypeEnum.ERROR.getValue(),
                                        pythonAgentEventConverter.buildErrorPayload(
                                                resolveErrorCode(throwable),
                                                resolveErrorMessage(throwable)
                                        )
                                )
                        )
                ));
    }

    private void ensureSidebarEnabled() {
        ThrowUtils.throwIf(!agentFeatureProperties.getSidebar().isEnabled(),
                ErrorCode.FORBIDDEN_ERROR, "Agent sidebar is disabled");
    }

    private String resolveErrorCode(Throwable throwable) {
        if (throwable instanceof BusinessException) {
            BusinessException businessException = (BusinessException) throwable;
            return String.valueOf(businessException.getCode());
        }
        return String.valueOf(ErrorCode.SYSTEM_ERROR.getCode());
    }

    private String resolveErrorMessage(Throwable throwable) {
        if (throwable instanceof BusinessException) {
            BusinessException businessException = (BusinessException) throwable;
            if (businessException.getMessage() != null) {
                return businessException.getMessage();
            }
        }
        if (throwable != null && throwable.getMessage() != null) {
            return throwable.getMessage();
        }
        return "Agent sidebar request failed";
    }
}
