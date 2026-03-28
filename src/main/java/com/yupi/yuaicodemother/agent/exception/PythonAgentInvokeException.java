package com.yupi.yuaicodemother.agent.exception;

public class PythonAgentInvokeException extends RuntimeException {

    public PythonAgentInvokeException(String message) {
        super(message);
    }

    public PythonAgentInvokeException(String message, Throwable cause) {
        super(message, cause);
    }
}
