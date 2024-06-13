import { goToHedyPage } from "../tools/navigation/nav";

describe('Error code gives correct error', () => {
    describe('Misspelled Keyword', () => {
        it('tests the print keyword', () => {
            const error_code = "prnt Hello world!"
            const error_message = `prnt is not a Hedy level 1 command. Did you mean print?`;
            goToHedyPage();

            cy.get('#editor > .cm-editor > .cm-scroller > .cm-content').click();
            cy.focused().type(error_code);

            cy.intercept('/parse').as('parse')
            cy.get('#runit').click();
            cy.wait('@parse')
            cy.get('#errorbox').should('be.visible').should('contain', error_message);
        })

        it('tests the ask keyword', () => {
            const error_code = "print Hello world!\nak Hello world?"
            const error_message = `ak is not a Hedy level 1 command. Did you mean ask?`;
            goToHedyPage();

            cy.get('#editor > .cm-editor > .cm-scroller > .cm-content').click();
            cy.focused().type(error_code);

            cy.intercept('/parse').as('parse')
            cy.get('#runit').click();
            cy.wait('@parse')
            cy.get('#errorbox').should('be.visible').should('contain', error_message);
        })
    })

    it('Missing Command', () => {
        const error_code = "hello world"
        const error_message = `You missed a command on line 1`;
        goToHedyPage();
    
        cy.get('#editor > .cm-editor > .cm-scroller > .cm-content').click();
        cy.focused().type(error_code);
    
        cy.intercept('/parse').as('parse')
        cy.get('#runit').click();
        cy.wait('@parse')
        cy.get('#errorbox').should('be.visible').should('contain', error_message);
    })

    it('Invalid Argument Type', () => {
        const error_code = "forward lalala"
        const error_message = `forward doesn't work with lalala because it is text. Change lalala to a number or input from ask.`;
        goToHedyPage();

        cy.get('#editor > .cm-editor > .cm-scroller > .cm-content').click();
        cy.focused().type(error_code);

        cy.intercept('/parse').as('parse')
        cy.get('#runit').click();
        cy.wait('@parse')
        cy.get('#errorbox').should('be.visible').should('contain', error_message);
    })

    it('Invalid Argument', () => {
        const error_code = "turn test"
        const error_message = `You can't use command turn with  test. Change  test to right or left.`;
        goToHedyPage();
    
        cy.get('#editor > .cm-editor > .cm-scroller > .cm-content').click();
        cy.focused().type(error_code);
    
        cy.intercept('/parse').as('parse')
        cy.get('#runit').click();
        cy.wait('@parse')
        cy.get('#errorbox').should('be.visible').and('contain', error_message);
    })
})