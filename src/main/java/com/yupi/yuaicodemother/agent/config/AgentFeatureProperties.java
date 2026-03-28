package com.yupi.yuaicodemother.agent.config;

import lombok.Data;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Data
@Configuration
@ConfigurationProperties(prefix = "agent")
public class AgentFeatureProperties {

    private final Sidebar sidebar = new Sidebar();

    private final Python python = new Python();

    @Data
    public static class Sidebar {

        private boolean enabled = false;
    }

    @Data
    public static class Python {

        private String baseUrl = "http://127.0.0.1:8000";

        private String internalToken = "";

        private int connectTimeoutMs = 3000;

        private int readTimeoutMs = 60000;
    }
}
