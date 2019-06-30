/**
 * Main Cell Component
 */

import {Component} from './Component';
import {h} from 'maquette';

/**
 * About Replacements
 * --------------------
 * This component has a one
 * regular-kind replacement:
 * * `child`
 */

/**
 * About Named Children
 * --------------------
 * `child` (single) - The child cell that is wrapped
 */
class Main extends Component {
    constructor(props, ...args){
        super(props, ...args);

        // Bind component methods
        this.makeChild = this.makeChild.bind(this);
    }

    render(){
        return (
            h('main', {
                id: this.props.id,
                class: "py-md-2",
                "data-cell-id": this.props.id,
                "data-cell-type": "Main"
            }, [
                h('div', {class: "container-fluid"}, [
                    this.makeChild()
                ])
            ])
        );
    }

    makeChild(){
        if(this.usesReplacements){
            return this.getReplacementElementFor('child');
        } else {
            return this.renderChildNamed('child');
        }
    }
}

export {Main, Main as default};