#   Copyright 2017-2019 typed_python Authors
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.


from typed_python import PointerTo, _types
from typed_python.compiler.type_wrappers.wrapper import Wrapper
from typed_python.compiler.type_wrappers.one_of_wrapper import OneOfWrapper
import typed_python.compiler.native_ast as native_ast
import typed_python.compiler

typeWrapper = lambda x: typed_python.compiler.python_object_representation.typedPythonTypeToTypeWrapper(x)


class PythonTypedFunctionWrapper(Wrapper):
    is_pod = True
    is_empty = True
    is_pass_by_ref = False

    def __init__(self, f):
        super().__init__(f)

    def getNativeLayoutType(self):
        return native_ast.Type.Void()

    def convert_call(self, context, left, args, kwargs):
        if kwargs:
            raise NotImplementedError("can't dispatch to native code with kwargs yet as our matcher doesn't understand it")

        if len(self.typeRepresentation.overloads) == 1:
            overload = self.typeRepresentation.overloads[0]
            functionObj = overload.functionObj

            if hasattr(functionObj, "__typed_python_no_compile__"):
                returnType = overload.returnType or object

                callRes = context.constantPyObject(functionObj).convert_call(
                    args, kwargs
                )

                if callRes is None:
                    return None

                return callRes.convert_to_type(returnType)

        callTarget = self.compileCall(
            context.functionContext.converter,
            None,
            [a.expr_type for a in args],
            None
        )
        if not callTarget:
            context.pushException(TypeError, f"Failed to dispatch to {self} with args {args}")
            return

        return context.call_typed_call_target(callTarget, args, {})

    @staticmethod
    def pickCallSignatureToImplement(overload, argTypes):
        """Pick the actual signature to use when calling 'overload' with 'argTypes'

        We can have a function like f(x: int), where we always know the signature.
        But for something like f(x), we may need to generate a different signature
        for each possible 'x' we pass it.

        Args:
            overload - a typed_python.internal.FunctionOverload
            argTypes - a list of typed_python Type objects

        Returns:
            a typed_python.Function object representing the signature we'll implement
            for this overload.
        """
        argTuples = []

        if len(argTypes) != len(overload.args):
            raise Exception(f"Signature mismatch; can't call {overload} with {argTypes}")

        for i, arg in enumerate(overload.args):
            # when choosing the signature we want to generate for a given call signature,
            # we specialize anything with _no signature at all_, but otherwise take the given
            # signature. Otherwise, we'd produce an exorbitant number of signatures (for every
            # possible subtype combination we encounter in code).

            if arg.typeFilter is None:
                argType = argTypes[i].typeRepresentation
            else:
                argType = arg.typeFilter or object

            argTuples.append(
                (arg.name, argType, arg.defaultValue, arg.isStarArg, arg.isKwarg)
            )

        return _types.Function(
            overload.name,
            overload.returnType or object,
            None,
            tuple(argTuples)
        )

    def compileCall(self, converter, returnType, argTypes, callback):
        """Compile this function being called with a particular signature.

        Args:
            converter - the PythonToNativeConverter that needs the concrete definition.
            returnType - the typed_python Type of what we're returning, or None if we don't know
            argTypes - (ListOf(wrapper)) a the actual concrete type wrappers for the arguments
                we're passing.
            callback - the callback to pass to 'convert' so that we can install the compiled
                function pointer in the class vtable at link time.

        Returns:
            a TypedCallTarget, or None
        """
        overloadAndIsExplicit = PythonTypedFunctionWrapper.pickSingleOverloadForCall(self.typeRepresentation, argTypes)

        if overloadAndIsExplicit is not None:
            overload = overloadAndIsExplicit[0]

            # just one overload will do. We can just instantiate this particular function
            # with a signature that comes from the method overload signature itself.
            return converter.convert(
                overload.functionObj,
                argTypes,
                returnType,
                callback=callback
            )

        if returnType is None:
            # we have to take the union of the return types we might be dispatching to
            possibleTypes = PythonTypedFunctionWrapper.determinePossibleReturnTypes(
                converter,
                self.typeRepresentation,
                argTypes
            )

            print("Possible return types are ", possibleTypes)

            returnType = OneOfWrapper.mergeTypes(possibleTypes)

            if returnType is None:
                return None

        return converter.defineNativeFunction(
            f'implement_function.{self}{argTypes}->{returnType}',
            ('implement_function.', self, returnType, tuple(argTypes)),
            list(argTypes),
            returnType,
            lambda context, outputVar, *args: (
                self.generateMethodImplementation(context, returnType, args)
            ),
            callback=callback
        )

    @staticmethod
    def overloadMatchesSignature(overload, argTypes, isExplicit):
        """Is it possible we could dispatch to FunctionOverload 'overload' with 'argTypes'?

        Returns:
            True if we _definitely_ match
            "Maybe" if we might match
            False if we definitely don't match the arguments.
        """
        if not (len(argTypes) == len(overload.args) and not any(x.isStarArg or x.isKwarg for x in overload.args)):
            return False

        allTrue = True
        for i in range(len(argTypes)):
            canConvert = argTypes[i].can_convert_to_type(typeWrapper(overload.args[i].typeFilter or object), isExplicit)

            if canConvert is False:
                return False
            elif canConvert == "Maybe":
                allTrue = False

        if allTrue:
            return allTrue
        else:
            return "Maybe"

    @staticmethod
    def determinePossibleReturnTypes(converter, func, argTypes):
        returnTypes = []

        for isExplicit in [False, True]:
            for o in func.overloads:
                # check each overload that we might match.
                mightMatch = PythonTypedFunctionWrapper.overloadMatchesSignature(o, argTypes, isExplicit)

                if mightMatch is False:
                    pass
                else:
                    if o.returnType is not None:
                        returnTypes.append(o.returnType)
                    else:
                        callTarget = converter.convert(o.functionObj, argTypes, None)

                        if callTarget is not None:
                            returnTypes.append(callTarget.output_type)

                    if mightMatch is True:
                        return returnTypes

        return returnTypes

    @staticmethod
    def pickSingleOverloadForCall(func, argTypes):
        """See if there is a single function overload that might match 'argTypes' and nothing else.

        Returns:
            None, or a tuple (FunctionOverload, explicit) indicating that one single overload
            is the one version of this function we might match.
        """

        possibleMaybe = None

        for isExplicit in [False, True]:
            for o in func.overloads:
                # check each overload that we might match.
                mightMatch = PythonTypedFunctionWrapper.overloadMatchesSignature(o, argTypes, isExplicit)

                if mightMatch is False:
                    pass
                elif mightMatch is True:
                    if possibleMaybe is not None:
                        if possibleMaybe == (o, False) and isExplicit:
                            return (o, True)
                        else:
                            return None
                    else:
                        return (o, isExplicit)
                else:
                    if possibleMaybe is None:
                        possibleMaybe = (o, isExplicit)
                    elif possibleMaybe == (o, False) and isExplicit:
                        possibleMaybe = (o, isExplicit)
                    else:
                        return None

        return possibleMaybe

    def generateMethodImplementation(self, context, returnType, args):
        """Generate native code that calls us with a given return type and set of arguments.

        We try each overload, first with 'isExplicit' as False, then with True. The first one that
        succeeds gets to produce the output.

        Args:
            context - an ExpressionConversionContext
            returnType - the output type we are expecting to return. This will be the union
                of the return types of all the overloads that might participate in this dispatch.
            args - the typed_expression for all of our actual arguments, which in this case
                are the instance, and then the actual arguments we want to convert.
        """
        func = self.typeRepresentation

        argTypes = [a.expr_type for a in args]

        def makeOverloadImplementor(overload, isExplicit):
            return lambda context, _, outputVar, *args: self.generateOverloadImplement(
                context, overload, isExplicit, outputVar, args
            )

        for isExplicit in [False, True]:
            for overloadIndex, overload in enumerate(func.overloads):
                mightMatch = self.overloadMatchesSignature(overload, argTypes, isExplicit)

                if mightMatch is not False:
                    overloadRetType = overload.returnType or object

                    testSingleOverloadForm = context.converter.defineNativeFunction(
                        f'implement_overload.{self}.{overloadIndex}.{isExplicit}.{argTypes}->{overloadRetType}',
                        ('implement_overload', self, overloadIndex, isExplicit, overloadRetType, tuple(argTypes)),
                        [PointerTo(overloadRetType)] + list(argTypes),
                        typeWrapper(bool),
                        makeOverloadImplementor(overload, isExplicit)
                    )

                    outputSlot = context.allocateUninitializedSlot(overloadRetType)

                    successful = context.call_typed_call_target(
                        testSingleOverloadForm,
                        (outputSlot.changeType(PointerTo(overloadRetType), False),) + args,
                        {}
                    )

                    with context.ifelse(successful.nonref_expr) as (ifTrue, ifFalse):
                        with ifTrue:
                            context.markUninitializedSlotInitialized(outputSlot)

                            # upcast the result
                            actualResult = outputSlot.convert_to_type(returnType)

                            if actualResult is not None:
                                context.pushReturnValue(actualResult)

                    # if we definitely match, we can return early
                    if mightMatch is True:
                        context.pushException(TypeError, f"Failed to find an overload for {self} matching {args}")
                        return

        # generate a cleanup handler for the cases where we don't match a method signature.
        # this should actually be hitting the interpreter instead.
        context.pushException(TypeError, f"Failed to find an overload for {self} matching {args}")

    def generateOverloadImplement(self, context, overload, isExplicit, outputVar, args):
        """Produce the code that implements this specific overload.

        The generated code returns control flow with a True if it fills out the 'outputVar'
        with data, and False otherwise.

        Args:
            context - an ExpressionConversionContext
            overload - the FunctionOverload we're trying to convert.
            isExplicit - are we using explicit conversion?
            outputVar - a TypedExpression(PointerTo(returnType)) we're supposed to initialize.
            args - the arguments to pass to the method (including the instance)
        """
        signature = self.pickCallSignatureToImplement(overload, [a.expr_type for a in args])

        argTypes = [a.typeFilter for a in signature.overloads[0].args]

        retType = overload.returnType or typeWrapper(object).typeRepresentation

        convertedArgs = []

        for argIx, argExpr in enumerate(args):
            argType = argTypes[argIx]

            convertedArg = context.allocateUninitializedSlot(argType)

            successful = argExpr.convert_to_type_with_target(convertedArg, isExplicit)

            with context.ifelse(successful.nonref_expr) as (ifTrue, ifFalse):
                with ifFalse:
                    context.pushTerminal(
                        native_ast.Expression.Return(arg=native_ast.const_bool_expr(False))
                    )

                with ifTrue:
                    context.markUninitializedSlotInitialized(convertedArg)

            convertedArgs.append(convertedArg)

        if outputVar.expr_type.typeRepresentation.ElementType != retType:
            raise Exception(f"Output type mismatch: {outputVar.expr_type.typeRepresentation} vs {retType}")

        res = context.call_py_function(overload.functionObj, convertedArgs, {}, typeWrapper(retType))

        if res is None:
            context.pushException(Exception, "unreachable")
            return

        outputVar.changeType(typeWrapper(retType), True).convert_copy_initialize(res)

        context.pushReturnValue(context.constant(True))
