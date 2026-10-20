from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from app.core.logging import get_logger
from app.security.model_scanner.report import ScanFinding, SeverityLevel

logger = get_logger(__name__)


class BaseDetector(ABC):
    @abstractmethod
    async def scan(self, path: Path) -> list[ScanFinding]:
        pass


class PickleDetector(BaseDetector):
    def __init__(self):
        self.dangerous_modules = {
            "subprocess",
            "os",
            "sys",
            "builtins",
            "__builtin__",
            "importlib",
            "pkgutil",
            "runpy",
            "code",
            "codeop",
            "compile",
            "exec",
            "eval",
            "open",
            "file",
            "socket",
            "urllib",
            "requests",
            "http",
            "ftplib",
            "telnetlib",
            "poplib",
            "imaplib",
            "smtplib",
            "nntplib",
            "xmlrpc",
            "marshal",
            "pickle",
            "shelve",
            "dbm",
            "sqlite3",
            "ctypes",
            "multiprocessing",
            "threading",
            "commands",
            "popen2",
        }

    async def scan(self, path: Path) -> list[ScanFinding]:
        findings = []

        for file_path in path.rglob("*.pkl"):
            findings.extend(self._scan_pickle_file(file_path))

        for file_path in path.rglob("*.pickle"):
            findings.extend(self._scan_pickle_file(file_path))

        for file_path in path.rglob("*.pkl.gz"):
            findings.extend(self._scan_pickle_file(file_path))

        return findings

    def _scan_pickle_file(self, file_path: Path) -> list[ScanFinding]:
        """Statically analyse a pickle file.

        The payload is *never* deserialised: `pickle.load` executes arbitrary
        code, so loading an untrusted pickle during a security scan would
        turn the scanner into a remote-code-execution vector. The opcode
        stream is inspected instead.
        """
        findings = []

        try:
            import pickletools

            with open(file_path, "rb") as f:
                data = f.read()

            # Disassemble the opcode stream; this never executes the payload.
            try:
                opcodes = list(pickletools.genops(data))
            except Exception as e:
                return [
                    ScanFinding(
                        detector="pickle_scanner",
                        finding_type="insecure_deserialization",
                        severity=SeverityLevel.MEDIUM,
                        description=f"Malformed pickle opcode stream: {e}",
                        file_path=str(file_path),
                        metadata={
                            "remediation": (
                                "Remove the pickle file or convert it to a safe format such as JSON."
                            )
                        },
                    )
                ]

            opcode_names = {opcode.name for opcode, _arg, _pos in opcodes}

            dangerous = {
                "GLOBAL": "imports an arbitrary global object",
                "STACK_GLOBAL": "imports an arbitrary global object",
                "REDUCE": "calls a callable, enabling code execution",
                "INST": "instantiates a class, enabling code execution",
                "OBJ": "instantiates a class, enabling code execution",
                "NEWOBJ": "instantiates a class, enabling code execution",
                "NEWOBJ_EX": "instantiates a class, enabling code execution",
                "BUILD": "mutates an object's state",
                "EXT1": "references an extension registry object",
                "EXT2": "references an extension registry object",
                "EXT4": "references an extension registry object",
            }

            for opcode, _arg, pos in opcodes:
                if opcode.name in dangerous:
                    findings.append(
                        ScanFinding(
                            detector="pickle_scanner",
                            finding_type="insecure_deserialization",
                            severity=SeverityLevel.CRITICAL,
                            description=(
                                f"Pickle opcode {opcode.name} at offset {pos} "
                                f"{dangerous[opcode.name]}"
                            ),
                            file_path=str(file_path),
                            metadata={
                                "opcode": opcode.name,
                                "offset": pos,
                                "remediation": (
                                    "Replace the pickle with a safe serialization format "
                                    "(JSON, MessagePack) or load it in an isolated sandbox."
                                ),
                            },
                        )
                    )

            if "PROTO" not in opcode_names and findings:
                findings.append(
                    ScanFinding(
                        detector="pickle_scanner",
                        finding_type="insecure_deserialization",
                        severity=SeverityLevel.LOW,
                        description="Pickle file does not declare a protocol version",
                        file_path=str(file_path),
                        metadata={
                            "remediation": "Re-serialise the file with an explicit protocol version."
                        },
                    )
                )

        except Exception as e:
            logger.warning("pickle_scan_failed", file_path=str(file_path), error=str(e))

        return findings

    def _analyze_object(self, obj: Any, file_path: str) -> list[ScanFinding]:
        findings = []

        if hasattr(obj, "__reduce__") or hasattr(obj, "__reduce_ex__"):
            findings.append(
                ScanFinding(
                    detector="PickleDetector",
                    finding_type="custom_reduce_method",
                    severity=SeverityLevel.HIGH,
                    description="Object has custom __reduce__ method which can execute arbitrary code",
                    file_path=file_path,
                    metadata={"object_type": type(obj).__name__},
                )
            )

        if hasattr(obj, "__class__"):
            class_name = obj.__class__.__name__
            module = obj.__class__.__module__

            if module in self.dangerous_modules or any(
                d in module for d in self.dangerous_modules
            ):
                findings.append(
                    ScanFinding(
                        detector="PickleDetector",
                        finding_type="dangerous_class",
                        severity=SeverityLevel.CRITICAL,
                        description=f"Object is instance of potentially dangerous class: {module}.{class_name}",
                        file_path=file_path,
                        metadata={"class": class_name, "module": module},
                    )
                )

        return findings


class JoblibDetector(BaseDetector):
    async def scan(self, path: Path) -> list[ScanFinding]:
        findings = []

        for file_path in path.rglob("*.joblib"):
            findings.extend(self._scan_joblib_file(file_path))

        for file_path in path.rglob("*.joblib.gz"):
            findings.extend(self._scan_joblib_file(file_path))

        for file_path in path.rglob("*.joblib.bz2"):
            findings.extend(self._scan_joblib_file(file_path))

        return findings

    def _scan_joblib_file(self, file_path: Path) -> list[ScanFinding]:
        findings = []

        try:
            import joblib

            obj = joblib.load(file_path)
            findings.extend(self._analyze_object(obj, str(file_path)))
        except Exception:
            pass

        return findings

    def _analyze_object(self, obj: Any, file_path: str) -> list[ScanFinding]:
        findings = []

        if hasattr(obj, "__reduce__") or hasattr(obj, "__reduce_ex__"):
            findings.append(
                ScanFinding(
                    detector="JoblibDetector",
                    finding_type="custom_reduce_method",
                    severity=SeverityLevel.HIGH,
                    description="Joblib object has custom __reduce__ method",
                    file_path=file_path,
                    metadata={"object_type": type(obj).__name__},
                )
            )

        return findings


class PyTorchDetector(BaseDetector):
    async def scan(self, path: Path) -> list[ScanFinding]:
        findings = []

        for file_path in path.rglob("*.pt"):
            findings.extend(self._scan_pytorch_file(file_path))

        for file_path in path.rglob("*.pth"):
            findings.extend(self._scan_pytorch_file(file_path))

        for file_path in path.rglob("*.bin"):
            findings.extend(self._scan_pytorch_file(file_path))

        return findings

    def _scan_pytorch_file(self, file_path: Path) -> list[ScanFinding]:
        findings = []

        try:
            import torch

            obj = torch.load(file_path, map_location="cpu", weights_only=True)

            if hasattr(obj, "state_dict"):
                findings.append(
                    ScanFinding(
                        detector="PyTorchDetector",
                        finding_type="state_dict_found",
                        severity=SeverityLevel.INFO,
                        description="PyTorch model state_dict found",
                        file_path=str(file_path),
                    )
                )

        except Exception:
            try:
                import pickle

                with open(file_path, "rb") as f:
                    obj = pickle.load(f)
                    if hasattr(obj, "__dict__") and "state_dict" in obj.__dict__:
                        findings.append(
                            ScanFinding(
                                detector="PyTorchDetector",
                                finding_type="pickle_in_pt_file",
                                severity=SeverityLevel.HIGH,
                                description="PyTorch file contains pickled object instead of state_dict",
                                file_path=str(file_path),
                            )
                        )
            except Exception:
                pass

        return findings


class TensorFlowDetector(BaseDetector):
    async def scan(self, path: Path) -> list[ScanFinding]:
        findings = []

        for file_path in path.rglob("*.h5"):
            findings.extend(self._scan_tf_file(file_path))

        for file_path in path.rglob("*.keras"):
            findings.extend(self._scan_tf_file(file_path))

        for file_path in path.rglob("*.pb"):
            findings.extend(self._scan_tf_file(file_path))

        for file_path in path.rglob("saved_model.pb"):
            findings.extend(self._scan_tf_file(file_path))

        return findings

    def _scan_tf_file(self, file_path: Path) -> list[ScanFinding]:
        findings = []

        try:
            import tensorflow as tf

            if file_path.suffix in [".h5", ".keras"]:
                try:
                    model = tf.keras.models.load_model(str(file_path))
                    findings.append(
                        ScanFinding(
                            detector="TensorFlowDetector",
                            finding_type="keras_model_found",
                            severity=SeverityLevel.INFO,
                            description="TensorFlow/Keras model loaded successfully",
                            file_path=str(file_path),
                            metadata={"model_type": "keras"},
                        )
                    )
                except Exception as e:
                    findings.append(
                        ScanFinding(
                            detector="TensorFlowDetector",
                            finding_type="load_failed",
                            severity=SeverityLevel.MEDIUM,
                            description=f"Failed to load TensorFlow model: {e!s}",
                            file_path=str(file_path),
                        )
                    )

        except ImportError:
            findings.append(
                ScanFinding(
                    detector="TensorFlowDetector",
                    finding_type="tensorflow_not_installed",
                    severity=SeverityLevel.INFO,
                    description="TensorFlow not available for scanning",
                    file_path=str(file_path),
                )
            )
        except Exception as e:
            findings.append(
                ScanFinding(
                    detector="TensorFlowDetector",
                    finding_type="scan_error",
                    severity=SeverityLevel.MEDIUM,
                    description=f"Error scanning TensorFlow file: {e!s}",
                    file_path=str(file_path),
                )
            )

        return findings


class ONNXDetector(BaseDetector):
    async def scan(self, path: Path) -> list[ScanFinding]:
        findings = []

        for file_path in path.rglob("*.onnx"):
            findings.extend(self._scan_onnx_file(file_path))

        return findings

    def _scan_onnx_file(self, file_path: Path) -> list[ScanFinding]:
        findings = []

        try:
            import onnx

            model = onnx.load(str(file_path))
            onnx.checker.check_model(model)

            findings.append(
                ScanFinding(
                    detector="ONNXDetector",
                    finding_type="onnx_model_valid",
                    severity=SeverityLevel.INFO,
                    description="ONNX model is valid",
                    file_path=str(file_path),
                    metadata={
                        "ir_version": model.ir_version,
                        "producer_name": model.producer_name,
                        "producer_version": model.producer_version,
                        "opset_imports": [f"{imp.domain}:{imp.version}" for imp in model.opset_import],
                    },
                )
            )

        except ImportError:
            findings.append(
                ScanFinding(
                    detector="ONNXDetector",
                    finding_type="onnx_not_installed",
                    severity=SeverityLevel.INFO,
                    description="ONNX not available for scanning",
                    file_path=str(file_path),
                )
            )
        except Exception as e:
            findings.append(
                ScanFinding(
                    detector="ONNXDetector",
                    finding_type="onnx_invalid",
                    severity=SeverityLevel.HIGH,
                    description=f"ONNX model validation failed: {e!s}",
                    file_path=str(file_path),
                )
            )

        return findings


class HuggingFaceDetector(BaseDetector):
    async def scan(self, path: Path) -> list[ScanFinding]:
        findings = []

        for file_path in path.rglob("*.bin"):
            findings.extend(self._scan_hf_file(file_path))

        for file_path in path.rglob("*.safetensors"):
            findings.extend(self._scan_hf_file(file_path))

        for file_path in path.rglob("config.json"):
            findings.extend(self._scan_config_file(file_path))

        return findings

    def _scan_hf_file(self, file_path: Path) -> list[ScanFinding]:
        findings = []

        try:
            from safetensors import safe_open

            with safe_open(str(file_path), framework="pt") as f:
                metadata = f.metadata()

            findings.append(
                ScanFinding(
                    detector="HuggingFaceDetector",
                    finding_type="safetensors_found",
                    severity=SeverityLevel.INFO,
                    description="SafeTensors file found",
                    file_path=str(file_path),
                    metadata=metadata or {},
                )
            )
        except ImportError:
            pass
        except Exception as e:
            findings.append(
                ScanFinding(
                    detector="HuggingFaceDetector",
                    finding_type="safetensors_error",
                    severity=SeverityLevel.MEDIUM,
                    description=f"Error reading SafeTensors: {e!s}",
                    file_path=str(file_path),
                )
            )

        return findings

    def _scan_config_file(self, file_path: Path) -> list[ScanFinding]:
        findings = []

        try:
            import json

            with open(file_path) as f:
                config = json.load(f)

            findings.append(
                ScanFinding(
                    detector="HuggingFaceDetector",
                    finding_type="config_found",
                    severity=SeverityLevel.INFO,
                    description="HuggingFace model config found",
                    file_path=str(file_path),
                    metadata={
                        "model_type": config.get("model_type"),
                        "architectures": config.get("architectures"),
                        "hidden_size": config.get("hidden_size"),
                        "num_layers": config.get("num_hidden_layers"),
                    },
                )
            )

            if "model_type" in config:
                if config["model_type"] in ["gpt2", "gpt_neo", "gptj", "llama", "bloom", "opt"]:
                    findings.append(
                        ScanFinding(
                            detector="HuggingFaceDetector",
                            finding_type="large_language_model",
                            severity=SeverityLevel.INFO,
                            description=f"Large language model detected: {config['model_type']}",
                            file_path=str(file_path),
                        )
                    )
        except Exception as e:
            findings.append(
                ScanFinding(
                    detector="HuggingFaceDetector",
                    finding_type="config_parse_error",
                    severity=SeverityLevel.LOW,
                    description=f"Error parsing config: {e!s}",
                    file_path=str(file_path),
                )
            )

        return findings
