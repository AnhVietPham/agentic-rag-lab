import logging
from contextlib import contextmanager
from typing import Any, Dict, Optional

from langfuse import Langfuse
from src.config import Settings

logger = logging.getLogger(__name__)

class LangfuseTracer: 
    def __init__(self, settings: Settings): 
        self.settings = settings.langfuse
        self.client: Optional[Langfuse] = None

        if (
            self.settings.enabled
            and self.settings.public_key
            and self.settings.secret_key
        ):
            try: 
                self.client = Langfuse(
                    public_key=self.settings.public_key,
                    secret_key=self.settings.secret_key,
                    host=self.settings.host,
                    flush_at=self.settings.flush_at,
                    flush_interval=self.settings.flush_interval,
                    debug=self.settings.debug,
                )
                logger.info(f"Langfuse tracing initialized (host: {self.settings.host})")
            except Exception as e:
                logger.error(f"Failed to initialize Langfuse: {e}")
                self.client = None
        else:
            logger.info("Langfuse tracing disabled or missing credentials")

    
    def get_callback_handler(
        self, 
        trace_name: Optional[str] = None,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
    ): 
        if not self.client: 
            return None

        try: 
            from langfuse.langchain import CallbackHandler

            handler = CallbackHandler(
                trace_name=trace_name, 
                user_id=user_id, 
                session_id=session_id,
                metadata=metadata,
                tags=tags,
            )
            return handler
        except Exception as e: 
            logger.error(f"Error creating CallbackHandler: {e}")
            return None

    @contextmanager
    def trace_langgraph_agent(
        self,
        name: str,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[list[str]] = None,
    ): 
        if not self.client: 
            yield None
            return 
        
        handler = self.get_callback_handler(
            trace_name=name, 
            user_id=user_id, 
            session_id=session_id,
            metadata=metadata,
            tags=tags
        )
        yield (None, handler)

    def get_trace_id(self, trace=None) -> Optional[str]:
        if not self.client:
            return None

        try: 
            trace_id = self.client.get_current_trace_id()
            return trace_id
        except Exception as e: 
            logger.error(f"Error getting trace ID: {e}")
            return None

    def submit_feedback(
        self, 
        trace_id: str, 
        score: float, 
        name: str = "user-feedback", 
        comment: Optional[str] = None,
    ) -> bool: 
        if not self.client:
            logger.warning("Cannot submit feedback: Langfuse is disabled")
            return False

        try: 
            self.client.score(
                trace_id=trace_id,
                name=name,
                value=score,
                comment=comment,
            )
            logger.info(f"Submitted feedback for trace {trace_id}: score={score}")
            return True
        except Exception as e:
            logger.error(f"Error submitting feedback: {e}")
            return False


    @contextmanager
    def trace_rag_request(
        self, 
        query: str, 
        user_id: Optional[str] = None, 
        session_id: Optional[str] = None, 
        metadata: Optional[Dict[str, Any]] = None,
    ): 
        if not self.client: 
            yield None
            return
        try:
            trace_legacy = getattr(self.client, "trace", None)
            if callable(trace_legacy):
                trace = trace_legacy(
                    name="rag_request",
                    input={"query": query},
                    metadata=metadata or {},
                    user_id=user_id,
                    session_id=session_id,
                )
                yield trace
                return
            # Langfuse v3+: root observation as span
            with self.client.start_as_current_span(name="rag_request") as span:
                span.update_trace(
                    user_id=user_id,
                    session_id=session_id,
                    input={"query": query},
                    metadata=metadata or {},
                )
                yield span
        except Exception as e:
            logger.error(f"Error creating Langfuse trace: {e}")
            yield None

    def create_span(
        self, 
        trace,
        name: str, 
        input_data: Optional[Dict[str, Any]] = None, 
        metadata: Optional[Dict[str, Any]] = None,
    ): 
        if not trace or not self.client: 
            return None
        
        try:
            # Langfuse v3: parent is a LangfuseSpan; child via start_span + .end()
            start_span = getattr(trace, "start_span", None)
            if callable(start_span):
                return start_span(
                    name=name,
                    input=input_data,
                    metadata=metadata or {},
                )
            span_legacy = getattr(self.client, "span", None)
            if callable(span_legacy):
                return span_legacy(
                    trace_id=trace.trace_id,
                    name=name,
                    input=input_data,
                    metadata=metadata or {},
                )
            logger.warning("Cannot create Langfuse span: client has no span API")
            return None
        except Exception as e:
            logger.error(f"Error creating span {name}: {e}")
            return None

    def create_generation(
        self,
        trace,
        name: str,
        model: str,
        input_data: Optional[Dict[str, Any]] = None,
        output: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        usage: Optional[Dict[str, Any]] = None,
    ): 
        if not trace or not self.client:
            return None

        try:
            start_gen = getattr(trace, "start_generation", None)
            if callable(start_gen):
                return start_gen(
                    name=name,
                    model=model,
                    input=input_data,
                    output=output,
                    metadata=metadata or {},
                )
            gen_legacy = getattr(self.client, "generation", None)
            if callable(gen_legacy):
                return gen_legacy(
                    trace_id=trace.trace_id,
                    name=name,
                    model=model,
                    input=input_data,
                    output=output,
                    metadata=metadata or {},
                    usage=usage,
                )
            logger.warning("Cannot create Langfuse generation: client has no generation API")
            return None
        except Exception as e:
            logger.error(f"Error creating generation {name}: {e}")
            return None

    def score_trace(
        self,
        trace,
        name: str,
        value: float,
        comment: Optional[str] = None,
    ):
        if not trace or not self.client:
            return

        try:
            tid = getattr(trace, "trace_id", None)
            if tid is not None:
                self.client.score(
                    trace_id=tid,
                    name=name,
                    value=value,
                    comment=comment,
                )
        except Exception as e:
            logger.error(f"Error scoring trace {name}: {e}")

    def update_span(
        self, 
        span, 
        output: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
        level: Optional[str] = None,
        status_message: Optional[str] = None,
    ): 
        if not span:
            return

        try:
            # For v2 API, we can update spans with end_time and output
            if output is not None:
                # Update the span with output data
                span.update(output=output)
            if metadata:
                span.update(metadata=metadata)
            if level:
                span.update(level=level)
            if status_message:
                span.update(status_message=status_message)
        except Exception as e:
            logger.error(f"Error updating span: {e}")

    def end_span(
        self, 
        span,
        output: Optional[Any] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ): 
        if not span:
            return

        try:
            # Update with final data if provided
            if output is not None or metadata is not None:
                self.update_span(span, output=output, metadata=metadata)

            # End the span to capture proper timing
            span.end()
        except Exception as e:
            logger.error(f"Error ending span: {e}")

    def flush(self):
        """Flush any pending traces."""
        if self.client:
            try:
                self.client.flush()
            except Exception as e:
                logger.error(f"Error flushing Langfuse: {e}")

    def shutdown(self):
        """Shutdown the Langfuse client."""
        if self.client:
            try:
                self.client.flush()
                self.client.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down Langfuse: {e}")