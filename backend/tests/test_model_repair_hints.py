import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.model_repairs import error_hint

def test_builtin_attribute_type_is_useful_without_customer_message_echo():
 error="AttributeError: 'int' object has no attribute 'lower'; actual customer text: private-business-value"
 hint=error_hint(error,'def main(query):\n return query.lower()')
 assert hint['receiver_type']=='int' and hint['attribute']=='lower' and 'private-business-value' not in str(hint)

def test_unknown_class_or_attribute_is_never_sent_as_an_identifier():
 hint=error_hint("AttributeError: 'PrivateCustomer' object has no attribute 'private_token'",'def main(q):\n return q.lower()')
 assert 'PrivateCustomer' not in str(hint) and 'private_token' not in str(hint)

def test_name_can_only_echo_an_identifier_already_in_previewed_code():
 assert error_hint("NameError: name 'math' is not defined",'def main(q):\n return math.floor(q)')['identifier']=='math'
 hint=error_hint("NameError: name 'private_customer_value' is not defined",'def main(q):\n return q')
 assert 'identifier' not in hint and 'private_customer_value' not in str(hint)

def test_operand_types_and_operator_not_actual_values_are_reported():
 hint=error_hint("TypeError: unsupported operand type(s) for +: 'int' and 'str'; actual: confidential",'def main(q):\n return q+1')
 assert hint['operator']=='+' and hint['left_type']=='int' and hint['right_type']=='str' and 'confidential' not in str(hint)

def test_json_and_division_failures_require_business_policy_not_silent_default():
 assert error_hint('ZeroDivisionError: division by zero; private-value','def main(q):\n return 1/q')['requires_user_policy']
 hint=error_hint('JSONDecodeError: private-contents','def main(q):\n return q')
 assert hint['requires_user_policy'] and 'private-contents' not in str(hint)
