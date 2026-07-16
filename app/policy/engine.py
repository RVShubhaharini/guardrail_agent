import yaml
from pathlib import Path
from typing import Dict, Any, List, Optional
from simpleeval import simple_eval, EvalWithCompoundTypes
from app.policy.templates import TEMPLATES
from app.config import settings

RULES_DIR = Path(__file__).parent / "rules"

class PolicyEngine:
    """Loads and evaluates security policy rules.
    Supports versioned YAML rule sets and pre-packaged templates."""

    def __init__(self, default_version: str = None):
        self.active_version = default_version or settings.active_policy_version
        self.rules = []
        self.active_template: Optional[str] = None
        self._load_rules()

    def _load_rules(self):
        # Reset template flag
        self.active_template = None
        
        # Load from YAML
        yaml_path = RULES_DIR / f"{self.active_version}.yaml"
        if not yaml_path.exists():
            # Fallback to v1 if requested version does not exist
            yaml_path = RULES_DIR / "v1.yaml"
            self.active_version = "v1"

        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f)
        self.rules = data.get("rules", [])

    def set_version(self, version: str):
        self.active_version = version
        self._load_rules()

    def load_template(self, template_name: str):
        if template_name.lower() in TEMPLATES:
            tpl = TEMPLATES[template_name.lower()]
            self.rules = tpl["rules"]
            self.active_template = template_name
            self.active_version = f"template:{template_name}"
            return True
        return False

    def evaluate(self, tool: str, params: dict, context: dict) -> List[dict]:
        """Evaluates rules against context. Returns a list of all matched rules.
        Each rule dictionary contains its configuration metadata."""
        eval_ctx = {
            "params": params,
            **context
        }
        
        norm_tool = tool.replace("gmail_", "").replace("db_", "")
        
        matched = []
        for rule in self.rules:
            # Check if this rule is targetted to this tool (or a wildcard '*' for any tool)
            target_tool = rule.get("tool", "*")
            norm_target = target_tool.replace("gmail_", "").replace("db_", "")
            
            if target_tool != "*" and target_tool != tool and norm_target != norm_tool:
                continue

            condition = rule.get("condition", "False")
            try:
                # Use EvalWithCompoundTypes to support list inclusions ("not in", "in")
                ev = EvalWithCompoundTypes(names=eval_ctx)
                condition_result = ev.eval(condition)
            except Exception as e:
                # Log evaluation failures instead of breaking evaluation
                print(f"Error evaluating rule '{rule.get('id')}': {e}")
                condition_result = False

            if condition_result:
                matched.append(rule)

        return matched

