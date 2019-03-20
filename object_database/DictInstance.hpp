#pragma once

#include "../typed_python/AllTypes.hpp"
#include "../typed_python/Instance.hpp"
#include "../typed_python/DictType.hpp"

/*******

A convenience wrapper around an Instance holding a Dict object.

*******/

template<class key_type, class value_type>
class DictInstance {
public:
    DictInstance(Type* keyType, Type* valueType) {
        mInstance = Instance::create(Dict::Make(keyType, valueType));
    }

    value_type* lookupKey(const key_type& key) {
        return (value_type*)((Dict*)mInstance.type())->lookupValueByKey(mInstance.data(), (instance_ptr)&key);
    }

    value_type* insertKey(const key_type& key) {
        return (value_type*)((Dict*)mInstance.type())->insertKey(mInstance.data(), (instance_ptr)&key);
    }

    bool deleteKey(const key_type& key) {
        return ((Dict*)mInstance.type())->deleteKey(mInstance.data(), (instance_ptr)&key);
    }

    value_type* lookupOrInsert(const key_type& key) {
        auto resPtr = lookupKey(key);

        if (resPtr) {
            return resPtr;
        }

        return insertKey(key);
    }

private:
    Instance mInstance;
};

