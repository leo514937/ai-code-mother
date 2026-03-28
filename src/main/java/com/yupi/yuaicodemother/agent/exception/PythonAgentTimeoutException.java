package com.yupi.yuaicodemother.agent.exception;

public class PythonAgentTimeoutException extends PythonAgentInvokeException {

    public PythonAgentTimeoutException(String message) {
        super(message);
    }

    public PythonAgentTimeoutException(String message, Throwable cause) {
        super(message, cause);
    }
}
