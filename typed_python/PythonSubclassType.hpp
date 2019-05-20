/******************************************************************************
   Copyright 2017-2019 Nativepython Authors

   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at

       http://www.apache.org/licenses/LICENSE-2.0

   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.
******************************************************************************/

#pragma once

#include "Type.hpp"

class PythonSubclass : public Type {
public:
    PythonSubclass(Type* base, PyTypeObject* typePtr) :
            Type(TypeCategory::catPythonSubclass)
    {
        m_base = base;
        mTypeRep = (PyTypeObject*)incref((PyObject*)typePtr);
        m_name = typePtr->tp_name;
        m_is_simple = false;

        forwardTypesMayHaveChanged();
    }

    bool isBinaryCompatibleWithConcrete(Type* other);

    template<class visitor_type>
    void _visitContainedTypes(const visitor_type& visitor) {
        visitor(m_base);
    }

    template<class visitor_type>
    void _visitReferencedTypes(const visitor_type& visitor) {
        visitor(m_base);
    }

    void _forwardTypesMayHaveChanged() {
        m_size = m_base->bytecount();
        m_is_default_constructible = m_base->is_default_constructible();
    }

    int32_t hash32(instance_ptr left) {
        return m_base->hash32(left);
    }

    template<class buf_t>
    void serialize(instance_ptr self, buf_t& buffer, size_t fieldNumber) {
        m_base->serialize(self, buffer, fieldNumber);
    }

    template<class buf_t>
    void deserialize(instance_ptr self, buf_t& buffer, size_t wireType) {
        m_base->deserialize(self, buffer, wireType);
    }

    void repr(instance_ptr self, ReprAccumulator& stream) {
        m_base->repr(self,stream);
    }

    bool cmp(instance_ptr left, instance_ptr right, int pyComparisonOp) {
        return m_base->cmp(left,right,pyComparisonOp);
    }

    void constructor(instance_ptr self) {
        m_base->constructor(self);
    }

    void destroy(instance_ptr self) {
        m_base->destroy(self);
    }

    void copy_constructor(instance_ptr self, instance_ptr other) {
        m_base->copy_constructor(self, other);
    }

    void assign(instance_ptr self, instance_ptr other) {
        m_base->assign(self, other);
    }

    static PythonSubclass* Make(Type* base, PyTypeObject* pyType);

    Type* baseType() const {
        return m_base;
    }

    PyTypeObject* pyType() const {
        return mTypeRep;
    }
};
