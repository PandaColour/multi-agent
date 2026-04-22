# 开发报告

## cloudbank-ags

<think>Let me start by exploring the codebase to understand the current implementation and then make the required changes.</think>

<think>Let me find the main source file first.</think>

<think>Good, I found the files. Let me read them.</think>

<think>Let me look for the ApplStatusEnum class in external dependencies or understand its API from how it's used. Let me also check the test files.</think>

<think>Now let me check the ResponseUtils class to understand how to create responses in tests, and also check the CustomerAgreementService for the backfillLoanAgreement method.</think>

<think>Now let me read the ResponseUtils to understand how to create responses in tests.</think>

<think>Let me read ResponseUtils.java and also the pom.xml to understand the test framework.</think>

<think>Now I have a clear understanding of the codebase. Let me proceed with the modifications:

1. Modify AuthFillJob.java - the two paths in backfill() method:
   - Fallback path (L121-128): Change from building status="04" PutOutResult to log.info + continue
   - Main path (L130-141): Add additional call to applQueryTargetFacade.queryApplByApplNoAddUser() to get applState, then use ApplStatusEnum.isFinalState() && !checkIsApproval() to check if credit was approved

2. Add new test cases to AuthFillJobTest.java:
   - UC-003a: Fallback path credit rejection
   - UC-003b: Main path credit rejection

Let me now make the modifications.

For AuthFillJob.java:

**Fallback path (L121-128):**
Current:
```java
// 授信失败终态
if (ApplStatusEnum.isFinalState(applOutput.getApplState())
        && !ApplStatusEnum.checkIsApproval(applOutput.getApplState())) {
    PutOutResult putOutResult = new PutOutResult();
    putOutResult.setLoanReqNo(customerAgreement.getBusinessNo());
    putOutResult.setCustNo(customerAgreement.getCustNo());
    putOutResult.setStatus("04");
    results.add(putOutResult);
}
```

Change to:
```java
// 授信失败终态，不上传、不作废，跳过并记录日志
if (ApplStatusEnum.isFinalState(applOutput.getApplState())
        && !ApplStatusEnum.checkIsApproval(applOutput.getApplState())) {
    log.info("授信流程协议回填JOB，降级路径授信拒绝跳过，协议号：{}，custNo：{}，businessNo：{}，applState：{}",
            customerAgreement.getAgreementNo(),
            customerAgreement.getCustNo(),
            customerAgreement.getBusinessNo(),
            applOutput.getApplState());
    continue;
}
```

For the main path, I need to retrieve the application output from the response and then check whether the credit approval status indicates a final state that isn't approved.

If the credit query returns successfully, I log the approval and set the status to "03" for the upload operation. Then I create a PutOutResult object with the loan request number, customer number, and contract details, storing it in the results list.

In the test case, I'm verifying that when the credit approval fails, the system correctly skips the upload by not calling the backfillLoanAgreement method. I need to verify that backfillLoanAgreement isn't called when the fallback path returns a rejected status, and I also need to check the main path scenario where the core query succeeds but the credit approval still fails. Let me check what ApplStatusEnum looks like to understand how to properly mock the rejection state.
</think>

<think>Now let me make the first modification to AuthFillJob.java - the fallback path (L121-128).</think>



Now I have a complete picture of the code. Let me implement the changes.

**Step 1: Modify the fallback path in AuthFillJob.java (L121-128)**

<think>Oops, I forgot the old_string parameter. Let me redo this properly.</think>

<think>I need to provide the old_string parameter. Let me redo this properly.</think>

<think>I need to provide both old_string and new_string. Let me do this correctly.</think>

<think>Now let me modify the main path (L130-141). I need to add a call to applQueryTargetFacade.queryApplByApplNoAddUser() after the core query succeeds, and then use ApplStatusEnum.isFinalState() && !checkIsApproval() to check if credit was approved.

The current main path (else branch) is:
```java
else {
    log.debug("授信流程协议回填JOB，核心成功");
    PutOutResult putOutResult = new PutOutResult();
    putOutResult.setLoanReqNo(customerAgreement.getBusinessNo());
    putOutResult.setCustNo(customerAgreement.getCustNo());
    putOutResult.setStatus("03");
    putOutResult.setContractNo(creditReqQueryOutputResponse.getData().getContractNo());
    HashMap<String, String> authMap = Maps.newHashMap();
    authMap.put("bfPartnerReqNo", creditReqQueryOutputResponse.getData().getPartnerRequestNo());
    putOutResult.setExtAttrs(authMap);
    results.add(putOutResult);
}
```

I need to add a call to applQueryTargetFacade.queryApplByApplNoAddUser() inside the else branch to retrieve the application output and validate the approval status before creating the PutOutResult.</think>

<think>Now let me modify the main path (else branch). I need to add a call to applQueryTargetFacade.queryApplByApplNoAddUser() inside the else block to check if credit was approved. The main path currently builds the PutOutResult directly after a successful core query. I need to:

1. After core query succeeds, call applQueryTargetFacade.queryApplByApplNoAddUser() to get applState
2. If applState indicates rejection (isFinalState && !checkIsApproval), log and continue
3. If query fails, log.warn and continue
4. If approved, keep the existing upload logic

Let me look at the current else block to craft the correct replacement.</think>



**Step 2: Modify the main path in AuthFillJob.java (L130-141)**

<think>Now let me verify the modified AuthFillJob.java looks correct.</think>



Let me verify the modified file:

<think>The file looks correct. Now let me update the test file to add the new test cases UC-003a and UC-003b.

For UC-003a (fallback path credit rejection):
- Mock contractQueryFacade to return failure (to trigger fallback path)
- Mock applQueryTargetFacade to return a rejection final state (applState that satisfies isFinalState && !checkIsApproval)
- Verify backfillLoanAgreement() is not called
- Verify results is empty

For UC-003b (main path credit rejection):
- Mock contractQueryFacade to return success with valid CreditReqQueryOutput


- Mock applQueryTargetFacade to return a rejection final state (to trigger the main path rejection check)
- Verify backfillLoanAgreement() is not called
- Verify results is empty

Now I need to look at the ApplOutput class to understand what fields it has available.</think>



Now let me update the tests. First, let me check what ApplOutput looks like:

<think>`ApplOutput` is from the external dependency `tech.qifu.jinke.targets.api.lps.modules.appl.domain.ApplOutput`, so I don't need to look at it. Now let me add the test cases.

Now let me add the test cases to AuthFillJobTest.java.
</think>

<think>Now let me add the new test cases to the AuthFillJobTest.java file. I need to add two new tests:
1. UC-003a: Fallback path credit rejection - contractQueryFacade fails, applQueryTargetFacade returns rejection final state
2. UC-003b: Main path credit rejection - contractQueryFacade succeeds, applQueryTargetFacade returns rejection final state

Looking at the existing test `testExecute_CoreFailureThenFallbackSuccess`, I can see how to structure the mocks. 

For ApplStatusEnum.isFinalState() && !ApplStatusEnum.checkIsApproval(), I need to find a status code that represents rejection (final state but not approval). 

I'll use "04" as the rejection state since that's consistent with the original code. For the test setup, I'm creating an ApplOutput with the rejection state, then mocking the necessary service calls to return either failure or rejection scenarios depending on which path I want to test.</think>



**Step 3: Add test cases UC-003a and UC-003b to AuthFillJobTest.java**

<think>Now I need to add the second part of UC-003b test and the original test method. Let me look at what the file looks like after the edit to make sure the content is correct.</think>



Now add the second half of UC-003b (the verify for backfill not being called):

<think>Good. Now let me read more to see the UC-003b test.</think>

<think>I can see the edit caused an issue - the old test `testExecute_ExceptionDuringExecution_UnlocksAndLogsError` got partially merged. Let me read the whole file and fix it.</think>

<think>I see the issue - the original `testExecute_ExceptionDuringExecution_UnlocksAndLogsError` test got partially merged into `testExecute_MainPath_CreditRejection_SkipsBackfill`. I need to fix this by properly separating the two tests.

The current state of the file shows that UC-003b test is missing its ending `}` and the `testExecute_ExceptionDuringExecution_UnlocksAndLogsError` test body is merged inside it. I need to fix this.

Let me replace the problematic section with the correct content.
</think>



The UC-003b test got partially merged with the original exception test. Let me fix this:

<think>I forgot to provide `new_string`. Let me provide it now.</think>

<think>Now let me verify the full test file looks correct.</think>



Now let me verify the final test file is correct:

<think>I see two issues:

1. Line 152: The Javadoc comment for UC-003a is missing the `*` prefix (it starts with `/**` but not `/**\n *` - it says `/**\n *` but actually it just says `/**\n/**` - wait let me re-read...

Looking at line 152: `/**` on a separate line, then the comment content. This is a formatting issue - it should be `/**` on the same line or with `*` on subsequent lines. But actually, in Java, `/**` on its own line starts a Javadoc, and then `*` on subsequent lines is the content. 

The Javadoc structure looks fine as-is. But there's a bigger problem - the last test `testExecute_ExceptionDuringExecution_UnlocksAndLogsError` is broken because `param` and `lockKey` are undefined in that scope since they're declared inside `testExecute_MainPath_CreditRejection_SkipsBackfill`. I need to look at the original test to see how it should be structured.

The original test declares those variables at the method level, so when the edit removed the variable declarations thinking they'd already been declared earlier, it created a reference to undefined variables. I need to restore the variable declarations and fix the test setup.</think>



The last test `testExecute_ExceptionDuringExecution_UnlocksAndLogsError` lost its variable declarations. Let me fix it:

<think>
I need to also provide new_string. Let me do it correctly.
</think>

<think>
Now let me also fix the formatting issue with the UC-003a comment (it starts with `/**` on a line by itself). Let me check the final file again to make sure everything is correct.
</think>

Now let me also fix the formatting of the UC-003a Javadoc comment (starts with `/**` on a separate line):

<think>
Now let me also check if `testExecute_SuccessfulBackFill` still works correctly - since I added a call to `applQueryTargetFacade.queryApplByApplNoAddUser()` in the main path, the existing test `testExecute_SuccessfulBackFill` doesn't mock `applQueryTargetFacade` for the main path success case. This test will likely fail because the mock doesn't return anything for `applQueryTargetFacade`.

Wait, but `testExecute_SuccessfulBackFill` uses a CreditReqQueryOutput with success status, so it goes to the main path. And now the main path calls `applQueryTargetFacade.queryApplByApplNoAddUser()`. 

The unmocked call will return null, which causes `checkIfFail()` or null data checks to fail and trigger a continue statement - meaning the upload gets skipped instead of executed. Since Mockito returns null by default for unstubbed methods, this mock setup needs to be updated for the test to pass.

Looking at the mock configuration more carefully, `anyString()` should match any string argument, so the mock should handle the call - but the return value needs to be set up properly for the test to verify the upload actually happens.

Since this is an existing test case (UC-001/UC-002) that should still work, I need to either stub `applQueryTargetFacade` to return a success response with an approval state, or adjust the existing test to accommodate the new behavior. Given the task description indicating these are existing behaviors that should remain unchanged, I should update the test setup to work with the new code path.
</think>

Now I need to check the existing `testExecute_SuccessfulBackFill` test - since the main path now calls `applQueryTargetFacade`, I need to add the mock for it:

<think>
The `testExecute_SuccessfulBackFill` test doesn't mock `applQueryTargetFacade`. Since the main path now calls `applQueryTargetFacade.queryApplByApplNoAddUser()`, and Mockito returns null by default, the test will fail. I need to add the mock to return a valid approval state (non-rejection) so that the upload still happens.

Let me update the test to add the ApplOutput mock with a valid approval state (like "03" or whatever represents approved).
</think>

I need to update `testExecute_SuccessfulBackFill` to mock `applQueryTargetFacade` for the main path success case:

<think>Now let me also verify the full final test file to make sure everything is correct.</think>



Now let me do a final verification of the complete test file:

<think>
The test file looks correct. Now let me update the todos and run the tests.
</think>

<think>
Now let me run the tests using Maven. Since this is a Maven project, I should run `mvn test`.
</think>

**Step 4: Run the tests**

<think>The command is running in the background. Let me wait for it to complete.</think>

<think>The test `testExecute_MainPath_CreditRejection_SkipsBackfill` failed because the backfillLoanAgreement was called. This means the `ApplStatusEnum.isFinalState("04") && !ApplStatusEnum.checkIsApproval("04")` returned `false`, meaning "04" is not a rejection state according to the actual `ApplStatusEnum`.

The issue is that "04" is not the actual rejection state code. The ApplStatusEnum checks the actual enum values, not the string "04". I need to use the actual rejection state code.

Let me check what ApplStatusEnum values look like. Since it's an external dependency, I can't see it directly. 

Looking at the error, the backfillLoanAgreement was invoked with a PutOutResult containing status="03", which means the code went through to the upload path instead of skipping it. The ApplOutput has `setApplState("04")` but the ApplStatusEnum.isFinalState() method must be checking something different—likely the actual enum values rather than the string representation.

I think the real problem is that ApplStatusEnum uses an enum type for applState, not a plain String. When I call `applOutput.setApplState("04")` with a String, it might not be converting properly to the enum that the enum methods expect, so the isFinalState() check is failing and the code proceeds to upload anyway.

I need to figure out what the actual ApplStatusEnum values are and use the proper enum type instead of trying to set a string. Let me trace through what the external dependency actually defines for the rejection states.

The real issue is that `ApplStatusEnum.isFinalState()` likely expects an enum type, not a String, so passing `"04"` won't work. Since I can't modify the external enum and the test doesn't show how the original code handled this, I should test with the actual rejection state values from the system. Looking at the test failure where status="03" was uploaded, it seems "04" isn't being recognized as a rejection state at all, which suggests the enum method is rejecting the string value and defaulting to a non-rejection path. I'm realizing the core issue: `ApplStatusEnum.isFinalState()` and `checkIsApproval()` probably expect an actual enum value rather than a string, so `setApplState("04")` with a string parameter might not work as intended. Since `CreditReqQueryOutput` doesn't expose an `applState` field, I need to reconsider whether mocking the rejection state is even possible without understanding the actual enum structure.</think>



The test failed because `ApplStatusEnum.isFinalState("04")` returned `false` - the enum likely uses its own enum constant type, not String. Let me check the ApplOutput class:

<think>Let me try a different approach - search in the broader cloudbank workspace.</think>

<think>Let me look for the ApplStatusEnum class in the target-api jar or similar.</think>

<think>I can't find the source file for ApplStatusEnum. Let me check the local Maven repository for the jar file and decompile it.</think>

<think>Let me try to find the ApplStatusEnum by looking at compiled classes or decompiling the jar. Let me check if there's a classes folder or something similar.</think>

<think>Let me look for the jar in a different way. Let me check the Maven local repository structure.</think>

<think>Let me try a broader search.</think>

## cloudbank-lcs

API Error: 400 {"error":{"message":"Budget has been exceeded! Current cost: 10.485363, Max budget: 10.0","type":"budget_exceeded","param":null,"code":"400"}}

## cloudbank-api

API Error: 400 {"error":{"message":"Budget has been exceeded! Current cost: 10.6152711, Max budget: 10.0","type":"budget_exceeded","param":null,"code":"400"}}

## cloudbank-common

API Error: 400 {"error":{"message":"Budget has been exceeded! Current cost: 10.6152711, Max budget: 10.0","type":"budget_exceeded","param":null,"code":"400"}}

## cloudbank-ods

API Error: 400 {"error":{"message":"Budget has been exceeded! Current cost: 10.9236141, Max budget: 10.0","type":"budget_exceeded","param":null,"code":"400"}}

## cloudbank-pcs

API Error: 400 {"error":{"message":"Budget has been exceeded! Current cost: 10.9236141, Max budget: 10.0","type":"budget_exceeded","param":null,"code":"400"}}

## cloudbank-partner

API Error: 400 {"error":{"message":"Budget has been exceeded! Current cost: 10.9236141, Max budget: 10.0","type":"budget_exceeded","param":null,"code":"400"}}
