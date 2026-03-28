package com.yupi.yuaicodemother.agent.exception;

public class PythonAgentProtocolException extends PythonAgentInvokeException {

    public PythonAgentProtocolException(String message) {
        super(message);
    }

    public PythonAgentProtocolException(String message, Throwable cause) {
        super(message, cause);
    }
}
