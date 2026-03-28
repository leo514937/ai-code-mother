package com.yupi.yuaicodemother.agent.config;

import io.netty.channel.ChannelOption;
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.client.reactive.ReactorClientHttpConnector;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.util.UriComponentsBuilder;
import reactor.netty.http.client.HttpClient;

@Configuration
public class AgentHttpClientConfig {

    @Bean(name = "agentWebClient")
    public WebClient agentWebClient(AgentFeatureProperties agentFeatureProperties) {
        AgentFeatureProperties.Python python = agentFeatureProperties.getPython();
        HttpClient httpClient = HttpClient.create()
                .option(ChannelOption.CONNECT_TIMEOUT_MILLIS, python.getConnectTimeoutMs())
                .responseTimeout(Duration.ofMillis(python.getReadTimeoutMs()));

        return WebClient.builder()
                .baseUrl(normalizeBaseUrl(python.getBaseUrl()))
                .defaultHeader(HttpHeaders.ACCEPT, MediaType.TEXT_EVENT_STREAM_VALUE)
                .clientConnector(new ReactorClientHttpConnector(httpClient))
                .build();
    }

    private String normalizeBaseUrl(String baseUrl) {
        return UriComponentsBuilder.fromHttpUrl(baseUrl.trim()).build().toUriString();
    }
}
