# ATLAS Autonomous Test Generation Report
**Verdict:** PASS

## Summary
- **Functions Analyzed:** 6
- **Selected Layers:** UNIT

## Layer Results
### UNIT - test.is_even
- **Confidence:** 0%

#### 🚨 Execution Failures
The following errors were encountered during test execution:
```text
===================================
_______ TestAdd.test_add_should_return_sum_when_positive_numbers_given ________

self = <test_test_add.TestAdd object at 0x000002449B290990>

    def test_add_should_return_sum_when_positive_numbers_given(self):
        # Arrange
        a = 2
        b = 3
        expected_result = 5
    
        # Act
>       result = TestAdd().add(a, b)
                 ^^^^^^^^^^^^^
E       AttributeError: 'TestAdd' object has no attribute 'add'

..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py:11: AttributeError
_______ TestAdd.test_add_should_return_sum_when_negative_numbers_given ________

self = <test_test_add.TestAdd object at 0x000002449EE0EB50>

    def test_add_should_return_sum_when_negative_numbers_given(self):
        # Arrange
        a = -2
        b = -3
        expected_result = -5
    
        # Act
>       result = TestAdd().add(a, b)
                 ^^^^^^^^^^^^^
E       AttributeError: 'TestAdd' object has no attribute 'add'

..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py:23: AttributeError
_________ TestAdd.test_add_should_return_sum_when_mixed_numbers_given _________

self = <test_test_add.TestAdd object at 0x000002449EE0E790>

    def test_add_should_return_sum_when_mixed_numbers_given(self):
        # Arrange
        a = 2
        b = -3
        expected_result = -1
    
        # Act
>       result = TestAdd().add(a, b)
                 ^^^^^^^^^^^^^
E       AttributeError: 'TestAdd' object has no attribute 'add'

..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py:35: AttributeError
_____________ TestAdd.test_add_should_return_sum_when_zero_given ______________

self = <test_test_add.TestAdd object at 0x000002449EE0F110>

    def test_add_should_return_sum_when_zero_given(self):
        # Arrange
        a = 0
        b = 0
        expected_result = 0
    
        # Act
>       result = TestAdd().add(a, b)
                 ^^^^^^^^^^^^^
E       AttributeError: 'TestAdd' object has no attribute 'add'

..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py:47: AttributeError
____ TestAdd.test_add_should_not_raise_error_when_non_numeric_input_given _____

self = <test_test_add.TestAdd object at 0x000002449EE0F710>

    def test_add_should_not_raise_error_when_non_numeric_input_given(self):
        # Arrange
        a = 'a'
        b = 2
    
        # Act and Assert
        with pytest.raises(TypeError):
>           TestAdd().add(a, b)
            ^^^^^^^^^^^^^
E           AttributeError: 'TestAdd' object has no attribute 'add'

..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py:59: AttributeError
===========================
```
<details><summary>Raw Pytest Output</summary>

```text
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.0.3, pluggy-1.6.0 -- C:\Users\yogesh kumar N\Downloads\ATLAS_AI_AGENT\.venv\Scripts\python.exe
cachedir: .pytest_cache
rootdir: C:\Users\yogesh kumar N
plugins: anyio-4.13.0, langsmith-0.8.14, asyncio-1.4.0, cov-7.1.0
asyncio: mode=Mode.STRICT, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collecting ... collected 5 items

..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py::TestAdd::test_add_should_return_sum_when_positive_numbers_given FAILED [ 20%]
..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py::TestAdd::test_add_should_return_sum_when_negative_numbers_given FAILED [ 40%]
..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py::TestAdd::test_add_should_return_sum_when_mixed_numbers_given FAILED [ 60%]
..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py::TestAdd::test_add_should_return_sum_when_zero_given FAILED [ 80%]
..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py::TestAdd::test_add_should_not_raise_error_when_non_numeric_input_given FAILED [100%]

================================== FAILURES ===================================
_______ TestAdd.test_add_should_return_sum_when_positive_numbers_given ________

self = <test_test_add.TestAdd object at 0x000002449B290990>

    def test_add_should_return_sum_when_positive_numbers_given(self):
        # Arrange
        a = 2
        b = 3
        expected_result = 5
    
        # Act
>       result = TestAdd().add(a, b)
                 ^^^^^^^^^^^^^
E       AttributeError: 'TestAdd' object has no attribute 'add'

..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py:11: AttributeError
_______ TestAdd.test_add_should_return_sum_when_negative_numbers_given ________

self = <test_test_add.TestAdd object at 0x000002449EE0EB50>

    def test_add_should_return_sum_when_negative_numbers_given(self):
        # Arrange
        a = -2
        b = -3
        expected_result = -5
    
        # Act
>       result = TestAdd().add(a, b)
                 ^^^^^^^^^^^^^
E       AttributeError: 'TestAdd' object has no attribute 'add'

..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py:23: AttributeError
_________ TestAdd.test_add_should_return_sum_when_mixed_numbers_given _________

self = <test_test_add.TestAdd object at 0x000002449EE0E790>

    def test_add_should_return_sum_when_mixed_numbers_given(self):
        # Arrange
        a = 2
        b = -3
        expected_result = -1
    
        # Act
>       result = TestAdd().add(a, b)
                 ^^^^^^^^^^^^^
E       AttributeError: 'TestAdd' object has no attribute 'add'

..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py:35: AttributeError
_____________ TestAdd.test_add_should_return_sum_when_zero_given ______________

self = <test_test_add.TestAdd object at 0x000002449EE0F110>

    def test_add_should_return_sum_when_zero_given(self):
        # Arrange
        a = 0
        b = 0
        expected_result = 0
    
        # Act
>       result = TestAdd().add(a, b)
                 ^^^^^^^^^^^^^
E       AttributeError: 'TestAdd' object has no attribute 'add'

..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py:47: AttributeError
____ TestAdd.test_add_should_not_raise_error_when_non_numeric_input_given _____

self = <test_test_add.TestAdd object at 0x000002449EE0F710>

    def test_add_should_not_raise_error_when_non_numeric_input_given(self):
        # Arrange
        a = 'a'
        b = 2
    
        # Act and Assert
        with pytest.raises(TypeError):
>           TestAdd().add(a, b)
            ^^^^^^^^^^^^^
E           AttributeError: 'TestAdd' object has no attribute 'add'

..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py:59: AttributeError
=========================== short test summary info ===========================
FAILED ..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py::TestAdd::test_add_should_return_sum_when_positive_numbers_given
FAILED ..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py::TestAdd::test_add_should_return_sum_when_negative_numbers_given
FAILED ..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py::TestAdd::test_add_should_return_sum_when_mixed_numbers_given
FAILED ..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py::TestAdd::test_add_should_return_sum_when_zero_given
FAILED ..\..\AppData\Local\Temp\tmpvagi6u1x\test_test_add.py::TestAdd::test_add_should_not_raise_error_when_non_numeric_input_given
============================== 5 failed in 0.60s ==============================


```
</details>
